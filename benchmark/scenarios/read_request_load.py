# Copyright 2015 ClusterHQ Inc.  See LICENSE file for details.
"""
Read request load scenario for the control service benchmarks.
"""

from zope.interface import implementer

from twisted.internet.defer import Deferred
from .._interfaces import IScenario, IRequestGenerator

from rate_measurer import DEFAULT_SAMPLE_SIZE

from request_load import (
    RequestLoadScenario, RequestOverload, RequestRateTooLow,
    RequestRateNotReached
)


@implementer(IRequestGenerator)
class ReadRequest(object):
    def __init__(self, reactor, cluster):
        self.control_service = cluster.get_control_service(reactor)

    def make_request(self):
        return self.control_service.list_nodes()


class ReadSetup(object):
    def __init__(self, reactor, cluster):
        self.control_service = cluster.get_control_service(reactor)

    def run_setup(self):
        d = Deferred()
        return d

@implementer(IRequestGenerator)
class ReadRequest(object):
    def __init__(self, reactor, cluster):
        self.control_service = cluster.get_control_service(reactor)

    def make_request(self):
        return self.control_service.list_nodes()


class ReadSetup(object):
    def __init__(self, reactor, cluster):
        self.control_service = cluster.get_control_service(reactor)

    def run_setup(self):
        d = Deferred()
        return d


@implementer(IScenario)
class ReadRequestLoadScenario(object):
    def __init__(self, reactor, cluster, request_rate=10,
                 sample_size=DEFAULT_SAMPLE_SIZE, timeout=45):
        self.read_request = ReadRequest(reactor, cluster)
        self.setup = None
        self.request_scenario = RequestLoadScenario(
            reactor,
            request_rate=request_rate,
            sample_size=sample_size,
            timeout=timeout,
            setup_instance=self.setup,
            request_generator_instance=self.read_request
        )

    def start(self):
        return self.request_scenario.start()

    def maintained(self):
        return self.request_scenario.maintained()

    def stop(self):
        return self.request_scenario.stop()


