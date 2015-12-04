# Copyright 2015 ClusterHQ Inc.  See LICENSE file for details.
"""
Read request load scenario for the control service benchmarks.
"""

import time
from zope.interface import implementer

from twisted.internet.defer import Deferred, succeed
from twisted.internet.task import LoopingCall

from flocker.common import gather_deferreds, loop_until

from .._interfaces import IScenario


class RateMeasurer(object):
    _sample_size = 5
    _count = 0
    _last_second = int(time.time())

    def __init__(self):
        self._counts = []

    def new_sample(self):
        now = int(time.time())
        if now > self._last_second:
            self._counts.append(self._count)
            self._counts = self._counts[-self._sample_size:]
            self._last_second = now
            self._count = 0
            print self._count, self._counts
        self._count += 1

    def rate(self):
        num_counts = len(self._counts)
        if num_counts == self._sample_size:
            return float(sum(self._counts) / float(num_counts))
        else:
            return float('nan')


class LoadGenerator(object):
    def __init__(self, request_generator, req_per_sec):
        self._request_generator = request_generator
        self.req_per_sec = req_per_sec
        self._loops = []
        self._starts = []

    def start(self):
        for i in range(self.req_per_sec):
            loop = LoopingCall(
                self._request_generator,
            )
            self._loops.append(loop)
            started = loop.start(interval=1)
            self._starts.append(started)

    def stop(self):
        for loop in self._loops:
            loop.stop()
        return gather_deferreds(self._starts)


class RequestRateTooLow(Exception):
    """
    The RequestRate dropped below a threshold.
    """


@implementer(IScenario)
class ReadRequestLoadScenario(object):
    """
    """

    def __init__(self, reactor, control_service, request_rate):
        self._maintained = Deferred()
        self.reactor = reactor
        self.control_service = control_service
        self.request_rate = request_rate
        self.rate_measurer = RateMeasurer()

    def _sample_and_return(self, result):
        self.rate_measurer.new_sample()
        return result

    def _request_and_measure(self):
        d = self.control_service.list_nodes()
        d.addCallback(self._sample_and_return)
        return d

    def start(self):
        """
        :return: A Deferred that fires when the desired scenario is
            established (e.g. that a certain load is being applied).
        """
        print "Starting scenario with rate: {}".format(self.request_rate)
        self.load_generator = LoadGenerator(
            request_generator=self._request_and_measure,
            req_per_sec=self.request_rate
        )
        self.load_generator.start()

        def reached_target_rate():
            current_rate = self.rate_measurer.rate()
            print "current rate", current_rate
            return current_rate >= self.request_rate

        waiting_for_target_rate = loop_until(self.reactor, reached_target_rate)

        def scenario_collapsed():
            return self.rate_measurer.rate() < self.request_rate

        # Start monitoring the scenario as soon as the target rate is reached.
        def monitor_scenario_status(result):
            scenario_monitor = loop_until(self.reactor, scenario_collapsed)
            scenario_monitor.addCallback(
                lambda ignored: self._maintained.errback(
                    RequestRateTooLow(self.rate_measurer.rate())
                )
            )
            return result

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
        return self.load_generator.stop()
