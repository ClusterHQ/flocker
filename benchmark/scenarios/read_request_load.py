# Copyright 2015 ClusterHQ Inc.  See LICENSE file for details.
"""
Read request load scenario for the control service benchmarks.
"""
from collections import deque
from itertools import repeat

from zope.interface import implementer
import eliot

from twisted.internet.defer import CancelledError, Deferred, succeed
from twisted.internet.task import LoopingCall

from flocker.common import loop_until, timeout

from .._interfaces import IScenario

DEFAULT_SAMPLE_SIZE = 5


class RateMeasurer(object):
    """
    Measures the rate of requests in requests per second
    """

    def __init__(self, sample_size=DEFAULT_SAMPLE_SIZE):
        self.counts = deque([0] * sample_size, sample_size)
        self.sent = 0
        self.received = 0
        self._rate = 0
        self.sample_size = sample_size

    def send_request(self):
        self.sent += 1

    def receive_request(self, result):
        self.received += 1

    def update_rate(self):
        self._rate = (self.received - self.counts[0]) / float(self.sample_size)
        self.counts.append(self.received)

    def outstanding(self):
        return self.sent - self.received

    def rate(self):
        return self._rate


class RequestRateTooLow(Exception):
    """
    The RequestRate dropped below a threshold.
    """


class RequestRateNotReached(Exception):
    """
    The RequestRate did not reach the target level.
    """


class RequestOverload(Exception):
    """
    There are too many outstanding requests
    """


@implementer(IScenario)
class ReadRequestLoadScenario(object):
    """
    A scenario that places load on the cluster by performing read
    requests at a specified rate.
    """

    def __init__(
        self, reactor, cluster, request_rate=10, interval=DEFAULT_SAMPLE_SIZE,
        timeout=45
    ):
        self._maintained = Deferred()
        self.reactor = reactor
        self.control_service = cluster.get_control_service(reactor)
        self.request_rate = request_rate
        self.interval = interval
        self.timeout = timeout
        self.rate_measurer = RateMeasurer(interval)
        self.max_outstanding = 10 * request_rate
        # Send requests per second
        self.loop = LoopingCall.withCount(self._request_and_measure)
        self.loop.clock = self.reactor
        self.monitor_loop = LoopingCall(self.check_rate)
        self.monitor_loop.clock = self.reactor

    def _request_and_measure(self, count):
        for i in range(count):
            self.rate_measurer.update_rate()
        for i in range(self.request_rate):
            d = self.control_service.list_nodes()
            self.rate_measurer.send_request()
            d.addCallbacks(self.rate_measurer.receive_request,
                           errback=eliot.write_failure)

    def _fail(self, exception):
        self.monitor_loop.stop()
        self._maintained.errback(exception)

    def check_rate(self):
        rate = self.rate_measurer.rate()
        if rate < self.request_rate:
            self._fail(RequestRateTooLow(rate))

        if self.rate_measurer.outstanding() > self.max_outstanding:
            self._fail(RequestOverload())

    def start(self):
        """
        :return: A Deferred that fires when the desired scenario is
            established (e.g. that a certain load is being applied).
        """
        self.loop.start(interval=1)

        def reached_target_rate():
            return self.rate_measurer.rate() >= self.request_rate

        def handle_timeout(failure):
            failure.trap(CancelledError)
            raise RequestRateNotReached

        waiting_for_target_rate = loop_until(self.reactor,
                                             reached_target_rate,
                                             repeat(1))
        timeout(self.reactor, waiting_for_target_rate, self.timeout)
        waiting_for_target_rate.addErrback(handle_timeout)

        # Start monitoring the scenario as soon as the target rate is reached.
        def monitor_scenario_status(result):
            self.monitor_loop.start(interval=1)

        waiting_for_target_rate.addCallback(monitor_scenario_status)

        return waiting_for_target_rate

    def maintained(self):
        """
        :return: A Deferred that fires with an errback if the desired
            scenario fails to hold between being established and being
            stopped.  This Deferred never fires with a callback.
        """
        return self._maintained

    def stop(self):
        """
        Stop the scenario from being maintained.

        :return: A Deferred that fires when the desired scenario is
            stopped.
        """
        if self.monitor_loop.running:
            self.monitor_loop.stop()

        if self.loop.running:
            self.loop.stop()

        return succeed(None)

