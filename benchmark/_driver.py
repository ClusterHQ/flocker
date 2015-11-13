# Copyright 2015 ClusterHQ Inc.  See LICENSE file for details.
"""
Driver for the control service benchmarks.
"""

from eliot import start_action
from eliot.twisted import DeferredContext

from twisted.python.components import proxyForInterface
from twisted.python.filepath import FilePath
from twisted.internet.task import cooperate
from twisted.internet.defer import maybeDeferred, Deferred

from flocker.apiclient import (
    IFlockerAPIV1Client, FakeFlockerClient, FlockerClient,
)


def benchmark(measure, operation, scenario, num_samples=3):
    """
    Perform sampling of the operation.

    :param measure: A quantity to measure.
    :param operation: An operation to perform.
    :param scenario: A load scenario.
    :param int num_samples: Number of samples to take.
    """
    running_scenario = scenario.start()

    samples = []

    def sample(i):
        with start_action(action_type=u'flocker:benchmark:sample', sample=i):
            sampling = DeferredContext(maybeDeferred(operation.get_probe))

            def run_probe(probe):
                probing = measure(probe.run)
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
        running_scenario.maintained().addErrback(
            stop_sampling_on_scenario_collapse)

        # Leaving the errback unhandled makes tests fail
        task.whenDone().addCallbacks(
            lambda ignored: collecting.callback(samples),
            lambda ignored: None)

        return collecting

    benchmarking = running_scenario.established().addCallback(collect_samples)

    def tear_down(result):
        stopping = running_scenario.stop()
        stopping.addCallback(lambda ignored: result)
        return stopping

    benchmarking.addBoth(tear_down)

    return benchmarking


class FastConvergingFakeFlockerClient(
    proxyForInterface(IFlockerAPIV1Client)
):
    def create_dataset(self, *a, **kw):
        result = self.original.create_dataset(*a, **kw)
        self.original.synchronize_state()
        return result

    def move_dataset(self, *a, **kw):
        result = self.original.move_dataset(*a, **kw)
        self.original.synchronize_state()
        return result

    def delete_dataset(self, *a, **kw):
        result = self.original.delete_dataset(*a, **kw)
        self.original.synchronize_state()
        return result

    def create_container(self, *a, **kw):
        result = self.original.create_container(*a, **kw)
        self.original.synchronize_state()
        return result

    def delete_container(self, *a, **kw):
        result = self.original.delete_container(*a, **kw)
        self.original.synchronize_state()
        return result


def driver(reactor, config, operation, measurement, scenario, result, output):

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
    else:
        control_service = FastConvergingFakeFlockerClient(FakeFlockerClient())

    d = control_service.version()

    def add_control_service(version, result):
        result['control_service'] = dict(
            host=config['control'],
            port=4523,
            flocker_version=version[u"flocker"],
        )

    d.addCallback(add_control_service, result)

    def run_benchmark(ignored):
        return benchmark(
            measurement(clock=reactor, control_service=control_service),
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
