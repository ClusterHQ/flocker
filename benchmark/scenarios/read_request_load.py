# Copyright 2015 ClusterHQ Inc.  See LICENSE file for details.
"""
Read request load scenario for the control service benchmarks.
"""

from zope.interface import implementer

from twisted.internet.defer import Deferred
from .._interfaces import IScenario, IRequestGenerator, IScenarioSetup

from ._rate_measurer import DEFAULT_SAMPLE_SIZE

from ._request_load import (
    RequestLoadScenario, RequestOverload, RequestRateTooLow,
    RequestRateNotReached
)


@implementer(IRequestGenerator)
class ReadRequest(object):
    """
    Implementation of the read request generator and the write.
    :ivar reactor: Reactor to use.
    :ivar cluster: `BenchmarkCluster` containing the control service.
    """
    def __init__(self, reactor, cluster):
        self.control_service = cluster.get_control_service(reactor)

    def make_request(self):
        return self.control_service.list_nodes()


@implementer(IRequestGenerator)
class ReadRequest(object):
    def __init__(self, reactor, cluster):
        self.control_service = cluster.get_control_service(reactor)

    def make_request(self):
        return self.control_service.list_nodes()


@implementer(IScenario)
class ReadRequestLoadScenario(object):
    """
    A scenario that places load on the cluster by performing read
    requests at a specified rate.

    :ivar reactor: Reactor to use.
    :ivar cluster: `BenchmarkCluster` containing the control service.
    :ivar request_rate: The target number of requests per second.
    :ivar sample_size: The number of samples to collect when measuring
        the rate.
    :ivar timeout: Maximum time in seconds to wait for the requested
        rate to be reached.
    """
    def __init__(self, reactor, cluster, request_rate=10,
                 sample_size=DEFAULT_SAMPLE_SIZE, timeout=45):
        self.read_request = ReadRequest(reactor, cluster)
        self.setup = None
        self.request_scenario = RequestLoadScenario(
            reactor,
            self.read_request,
            request_rate=request_rate,
            sample_size=sample_size,
            timeout=timeout,
            setup_instance=self.setup,
        )

    def start(self):
        return self.request_scenario.start()

    def maintained(self):
        return self.request_scenario.maintained()

    def stop(self):
        return self.request_scenario.stop()


