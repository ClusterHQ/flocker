from datetime import datetime
import json
from os import environ, getcwd
from platform import node, platform
from sys import stdout

from eliot import start_action
from eliot.twisted import DeferredContext

from twisted.python.components import proxyForInterface
from twisted.python.filepath import FilePath
from twisted.internet.task import cooperate
from twisted.internet.defer import maybeDeferred, Deferred

from flocker import __version__ as flocker_client_version
from flocker.apiclient import (
    IFlockerAPIV1Client, FakeFlockerClient, FlockerClient,
)
from flocker.common import gather_deferreds

from benchmark_operations import get_operation
from benchmark_measurements import get_measurement
from benchmark_scenarios import get_scenario


def benchmark(measure, operation, scenario, n=3):
    """
    Perform sampling of the operation.

    :param measure: A quantity to measure.
    :param operation: An operation to perform.
    :param scenario: A load scenario.
    :param int n: Number of samples to take.
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
        task = cooperate(sample(i) for i in range(n))

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


def record_samples(
    samples, version, metric_name, measurement_name, out=stdout
):
    """
    Create a record from the samples and write it.

    :param samples: Sampling results.
    :param version: Flocker server version.
    :param metric_name: Sampled operation.
    :param measurement_name: Samples measurement.
    :param out: Output file for record.
    """
    timestamp = datetime.now().isoformat()
    artifact = dict(
        client=dict(
            flocker_version=flocker_client_version,
            date=timestamp,
            working_directory=getcwd(),
            username=environ[b"USER"],
            nodename=node(),
            platform=platform(),
        ),
        server=dict(
            flocker_version=version,
        ),
        measurement=measurement_name,
        metric_name=metric_name,
        samples=samples,
    )
    json.dump(artifact, out)


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


def driver(reactor, control_service_address=None, cert_directory=b"certs",
           metric_name=b"read-request", measurement_name=b"wallclock",
           scenario_name=b'ten_ro_req_sec'):

    if control_service_address:
        cert_directory = FilePath(cert_directory)
        client = FlockerClient(
            reactor,
            host=control_service_address,
            port=4523,
            ca_cluster_path=cert_directory.child(b"cluster.crt"),
            cert_path=cert_directory.child(b"user.crt"),
            key_path=cert_directory.child(b"user.key"),
        )
    else:
        client = FastConvergingFakeFlockerClient(FakeFlockerClient())

    metric = get_operation(client=client, name=metric_name)
    measurement = get_measurement(
        clock=reactor, client=client, name=measurement_name,
    )
    scenario = get_scenario(
        clock=reactor, client=client, name=scenario_name,
    )
    version = client.version()

    d = gather_deferreds((metric, measurement, scenario, version))

    def got_parameters((metric, measurement, scenario, version)):
        d = benchmark(measurement, metric, scenario)
        d.addCallback(
            record_samples,
            version[u"flocker"],
            metric_name,
            measurement_name
        )
        return d

    d.addCallback(got_parameters)
    # d.addErrback(lambda ignored: None)
    return d
