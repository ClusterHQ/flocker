# Copyright 2015 ClusterHQ Inc.  See LICENSE file for details.
"""
Driver for the control service benchmarks.
"""

from eliot import start_action
from eliot.twisted import DeferredContext

from twisted.python.filepath import FilePath
from twisted.internet.task import cooperate
from twisted.internet.defer import maybeDeferred, Deferred, succeed

from flocker.apiclient import FlockerClient


def benchmark(metric, operation, scenario, num_samples=3):
    """
    Perform sampling of the operation.

    :param IMetric metric: A quantity to measure.
    :param IOperation operation: An operation to perform.
    :param IScenario scenario: A load scenario.
    :param int num_samples: Number of samples to take.
    :return: Deferred firing with a list of samples. Each sample is a
        dictionary containing a ``success`` boolean. If ``success is True``,
        the dictionary also contains a ``value`` for the sample measurement.
        If ``success is False``, the dictionary also contains a ``reason`` for
        failure.
    """
    scenario_established = scenario.start()

    samples = []

    def sample(i):
        with start_action(action_type=u'flocker:benchmark:sample', sample=i):
            sampling = DeferredContext(maybeDeferred(operation.get_probe))

            def run_probe(probe):
                probing = metric.measure(probe.run)
                probing.addCallbacks(
                    lambda interval: samples.append(
                        dict(success=True, value=interval)
                    ),
                    lambda reason: samples.append(
                        dict(success=False, reason=reason.getTraceback()),
                    ),
                )
                probing.addCallback(lambda ignored: probe.cleanup())
                return probing
            sampling.addCallback(run_probe)
            sampling.addActionFinish()
            return sampling.result

    def collect_samples(ignored):
        collecting = Deferred()
        task = cooperate(sample(i) for i in range(num_samples))

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

    def tear_down(result):
        stopping = scenario.stop()
        stopping.addCallback(lambda ignored: result)
        return stopping

    benchmarking.addBoth(tear_down)

    return benchmarking


def driver(reactor, config, operation, metric, scenario, result, output):
    """
    :param reactor: Reactor to use.
    :param config: Configuration read from options.
    :param IOperation operation: An operation to perform.
    :param IMetric metric: A quantity to measure.
    :param IScenario scenario: A load scenario.
    :param result: A dictionary which will be updated with values to
        create a JSON result.
    :param output: A callable to receive the JSON structure, for
        printing or storage.
    """

    if config['control']:
        cert_directory = FilePath(config['certs'])
        control_service = FlockerClient(
            reactor,
            host=config['control'],
            port=4523,
            ca_cluster_path=cert_directory.child(b"cluster.crt"),
            cert_path=cert_directory.child(b"user.crt"),
            key_path=cert_directory.child(b"user.key"),
        )

        d = control_service.version()
    else:
        # Only valid for operation 'no-op'
        control_service = None
        d = succeed({u'flocker': None})

    def add_control_service(version, result):
        result['control_service'] = dict(
            host=config['control'],
            port=4523,
            flocker_version=version[u"flocker"],
        )

    d.addCallback(add_control_service, result)

    def run_benchmark(ignored):
        return benchmark(
            metric(clock=reactor, control_service=control_service),
            operation(control_service=control_service),
            scenario(reactor, control_service)
        )

    d.addCallback(run_benchmark)

    def add_samples(samples, result):
        result['samples'] = samples
        return result

    d.addCallback(add_samples, result)

    d.addCallback(output)

    return d
