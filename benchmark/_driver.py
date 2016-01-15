# Copyright 2015 ClusterHQ Inc.  See LICENSE file for details.
"""
Driver for the control service benchmarks.
"""

from eliot import start_action
from eliot.twisted import DeferredContext

from twisted.internet.task import cooperate
from twisted.internet.defer import Deferred, logError, maybeDeferred


def bypass(result, func, *args, **kw):
    """
    Perform the function, but fire with the result from the previous Deferred.

    :param result: Value with which to fire returned Deferred.
    :param func: Function to call. This function has its return value ignored,
        except that if it returns a Deferred, wait for the Deferred to fire
        and ignore that result.
    :param args: Postional arguments to function ``func``.
    :param kw: Keyword arguments to function ``func``.
    :return: a Deferred that fires with ``result``.
    """
    d = maybeDeferred(func, *args, **kw)
    d.addErrback(logError)
    d.addBoth(lambda ignored: result)
    return d


def sample(operation, metric, name):
    """
    Perform sampling of the operation.

    :param IOperation operation: An operation to perform.
    :param IMetric metric: A quantity to measure.
    :param int name: Identifier for individual sample.
    :return: Deferred firing with a sample. A sample is a dictionary
        containing a ``success`` boolean.  If ``success is True``, the
        dictionary also contains a ``value`` for the sample measurement.
        If ``success is False``, the dictionary also contains a
        ``reason`` for failure.
    """
    with start_action(action_type=u'flocker:benchmark:sample', sample=name):
        sampling = DeferredContext(maybeDeferred(operation.get_probe))

        def run_probe(probe):
            probing = metric.measure(probe.run)
            probing.addCallback(
                lambda measurement: dict(success=True, value=measurement)
            )
            probing.addCallback(bypass, probe.cleanup)

            return probing
        sampling.addCallback(run_probe)

        # Convert an error running the probe into a failed sample.
        def convert_to_result(failure):
            return dict(success=False, reason=failure.getTraceback())
        sampling.addErrback(convert_to_result)

        return sampling.addActionFinish()


def benchmark(scenario, operation, metric, num_samples):
    """
    Perform benchmarking of the operation within a scenario.

    :param IScenario scenario: A load scenario.
    :param IOperation operation: An operation to perform.
    :param IMetric metric: A quantity to measure.
    :param int num_samples: Number of samples to take.
    :return: Deferred firing with a tuple containing one list of
        benchmark samples and one scenario metrics result. See the
        ``sample`` function for the structure of the samples.  The
        scenario metrics are a dictionary containing information about
        the scenario.
    """
    scenario_established = scenario.start()

    samples = []

    def collect_samples(ignored):
        collecting = Deferred()
        task = cooperate(
            sample(operation, metric, i).addCallback(samples.append)
            for i in range(num_samples))

        # If the scenario collapses, stop sampling
        def stop_sampling_on_scenario_collapse(failure):
            task.stop()
            collecting.errback(failure)
        scenario.maintained().addErrback(stop_sampling_on_scenario_collapse)

        # Leaving the errback unhandled makes tests fail
        task.whenDone().addCallbacks(
            lambda ignored: collecting.callback(samples),
            lambda ignored: None)

        return collecting

    benchmarking = scenario_established.addCallback(collect_samples)

    def stop_scenario(samples):
        d = scenario.stop()

        def combine_results(scenario_metrics):
            return (samples, scenario_metrics)
        d.addCallback(combine_results)

        return d
    benchmarking.addCallbacks(
        stop_scenario,
        bypass, errbackArgs=[scenario.stop]
    )

    return benchmarking


def driver(
    reactor, cluster, scenario_factory, operation_factory, metric_factory,
    num_samples, result, output
):
    """
    :param reactor: Reactor to use.
    :param BenchmarkCluster cluster: Benchmark cluster.
    :param callable scenario_factory: A load scenario factory.
    :param callable operation_factory: An operation factory.
    :param callable metric_factory: A metric factory.
    :param int num_samples: Number of samples to take.
    :param result: A dictionary which will be updated with values to
        create a JSON result.
    :param output: A callable to receive the JSON structure, for
        printing or storage.
    """

    d = cluster.get_control_service(reactor).version()

    def add_control_service(version, result):
        result['control_service'] = dict(
            host=cluster.control_node_address().compressed,
            flocker_version=version[u"flocker"],
        )

    d.addCallback(add_control_service, result)

    def run_benchmark(ignored):
        return benchmark(
            scenario_factory(reactor, cluster),
            operation_factory(reactor, cluster),
            metric_factory(reactor, cluster),
            num_samples,
        )

    d.addCallback(run_benchmark)

    def add_samples(outputs, result):
        samples, scenario_metrics = outputs
        result['samples'] = samples
        if scenario_metrics:
            result['scenario']['metrics'] = scenario_metrics
        return result

    d.addCallback(add_samples, result)

    d.addCallback(output)

    return d
