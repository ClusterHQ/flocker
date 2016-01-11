# Copyright 2015 ClusterHQ Inc.  See LICENSE file for details.
"""
Request load scenario for the control service benchmarks.
"""
from itertools import repeat

from zope.interface import implementer
from eliot import start_action, write_failure, Message
from eliot.twisted import DeferredContext

from twisted.internet.defer import CancelledError, Deferred
from twisted.internet.task import LoopingCall

from flocker.common import loop_until, timeout

from .._interfaces import IScenario
from ._rate_measurer import RateMeasurer, DEFAULT_SAMPLE_SIZE


class RequestRateTooLow(Exception):
    """
    The request rate dropped below a threshold.
    """


class RequestRateNotReached(Exception):
    """
    The request rate did not reach the target level.
    """


class RequestOverload(Exception):
    """
    There are too many outstanding requests.
    """


class NoNodesFound(Exception):
    """
    No nodes were provided by the control service.
    """


class RequestScenarioAlreadyStarted(Exception):
    """
    No nodes were provided by the control service.
    """


@implementer(IScenario)
class RequestLoadScenario(object):
    """
    A scenario that places load on the cluster by performing
    requests at a specified rate.

    :ivar reactor: Reactor to use.
    :ivar scenario_setup: provider of the interface
        ``IRequestScenarioSetup``.
    :ivar request_rate: The target number of requests per second.
    :ivar sample_size: The number of samples to collect when measuring
        the rate.
    :ivar timeout: Maximum time in seconds to wait for the requested
        rate to be reached.
    :ivar maintained: A ``Deferred`` that fires with an errback if the desired
        scenario fails to hold between being established and being
        stopped.  This Deferred never fires with a callback.
    :ivar rate_measurer: ``RateMeasurer`` instace to monitor the scenario.
    :ivar loop: main loop that will be doing requests every second.
    :ivar monitor_loop: loop that will monitor the status of the scenario once
        the target has been reached.
    :ivar is_started: boolean that will be set to True once the scenario has
        been started. The scenario cannot be started twice. If someone tries
        to do so, an exception will be raised.
    :ivar rate_tolerated: rate that will be consigered big enough to be a valid
        load given the request_rate requested and the tolerance_percentage.
    """

    def __init__(
        self, reactor, scenario_setup_instance, request_rate=10,
        sample_size=DEFAULT_SAMPLE_SIZE, timeout=45,
        tolerance_percentage=0.2
    ):
        """
        ``RequestLoadScenario`` constructor.

        :param reactor: Reactor to use.
        :param scenario_setup_instance: provider of the
            ``IRequestScenarioSetup`` interface.
        :param request_rate: target number of request per second.
        :param sample_size: number of samples to collect when measuring
            the rate.
        :param tolerance_percentage: error percentage in the rate that is
            considered valid. For example, if we request a ``request_rate``
            of 20, and we give a tolerance_percentage of 0.2 (20%), anything
            in [16,20] will be a valid rate.
        """
        self.reactor = reactor
        self.scenario_setup = scenario_setup_instance
        self.request_rate = request_rate
        self.timeout = timeout
        self._maintained = Deferred()
        self.rate_measurer = RateMeasurer(sample_size)
        self.max_outstanding = 10 * request_rate
        # Send requests per second
        self.loop = LoopingCall.withCount(self._request_and_measure)
        self.loop.clock = self.reactor
        # Monitor the status of the scenario
        self.monitor_loop = LoopingCall(self.check_rate)
        self.monitor_loop.clock = self.reactor
        self.is_started = False
        self.rate_tolerated = (
            float(request_rate) - (request_rate*tolerance_percentage)
        )

    def _request_and_measure(self, count):
        """
        Update the rate with the current value and send ``request_rate``
        number of new requests.

        :param count: The number of seconds passed since the last time
            ``_request_and_measure`` was called.
        """
        for i in range(count):
            self.rate_measurer.update_rate()

        def handle_request_error(result):
            self.rate_measurer.request_failed(result)
            write_failure(result)

        for i in range(self.request_rate):
            t0 = self.reactor.seconds()

            d = self.scenario_setup.make_request()

            def get_time(_ignore):
                return self.reactor.seconds() - t0
            d.addCallback(get_time)

            self.rate_measurer.request_sent()
            d.addCallbacks(
                self.rate_measurer.response_received,
                handle_request_error
            )

    def _fail(self, exception):
        """
        Fail the scenario. Stop the monitor loop and throw the
        error.

        :param exception: ``Exception`` that caused the failure.
        """
        self.monitor_loop.stop()
        self._maintained.errback(exception)

    def check_rate(self):
        """
        Verify that the rate hasn't decreased and that the scenario is
        not overloaded. A scenario is overloaded if there are too many
        outstanding requests.

        :raise RequestRateTooLow: if the rate has dropped.
        :raise RequestOverload: if the scenario is overloaded.
        """
        rate = self.rate_measurer.rate()
        if rate < self.rate_tolerated:
            self._fail(RequestRateTooLow(rate))

        elif self.rate_measurer.outstanding() > self.max_outstanding:
            self._fail(RequestOverload())

    def start(self):
        """
        Runs the setup and starts the scenario

        :return: A Deferred that fires when the desired scenario is
            established (e.g. that a certain load is being applied).

        :raise RequestScenarioAlreadyStarted: if the scenario had been
            already started.
        """
        # First, verify that the scenario has not been already started
        if self.is_started:
            raise RequestScenarioAlreadyStarted()
        else:
            self.is_started = True

        d = self.scenario_setup.run_setup()
        d.addCallback(self.run_scenario)
        return d

    def run_scenario(self, result):
        """
        :return: A Deferred that fires when the desired scenario is
            established (e.g. that a certain load is being applied).

        :raise RequestRateNotReached: if the target rate could not be
            reached.
        """
        self.loop.start(interval=1)

        def reached_target_rate():
            return self.rate_measurer.rate() >= self.rate_tolerated

        def handle_timeout(failure):
            failure.trap(CancelledError)
            raise RequestRateNotReached()

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
        :return: A ``Deferred`` that fires with an errback if the desired
            scenario fails to hold between being established and being
            stopped.  This Deferred never fires with a callback.
        """
        return self._maintained

    def stop(self):
        """
        Stop the scenario from being maintained by stopping all the
        loops that may be executing.

        :return Deferred[Optional[Dict[unicode, Any]]]: Scenario metrics.
        """
        self.is_started = False
        if self.monitor_loop.running:
            self.monitor_loop.stop()

        if self.loop.running:
            self.loop.stop()

        outstanding_requests = self.rate_measurer.outstanding()

        if outstanding_requests > 0:
            msg = (
                "There are {num_requests} outstanding requests. "
                "Waiting {num_seconds} seconds for them to complete."
            ).format(
                num_requests=outstanding_requests,
                num_seconds=self.timeout
            )
            Message.log(key='outstanding_requests', value=msg)

        with start_action(
            action_type=u'flocker:benchmark:scenario:stop',
            scenario='request_load'
        ):
            def no_outstanding_requests():
                return self.rate_measurer.outstanding() == 0

            scenario_stopped = loop_until(self.reactor,
                                          no_outstanding_requests,
                                          repeat(1))
            timeout(self.reactor, scenario_stopped, self.timeout)
            scenario = DeferredContext(scenario_stopped)

            def handle_timeout(failure):
                failure.trap(CancelledError)
                msg = (
                    "Force stopping the scenario. "
                    "There are {num_requests} outstanding requests"
                ).format(
                    num_requests=outstanding_requests
                )
                Message.log(key='force_stop_request', value=msg)
            scenario.addErrback(handle_timeout)

            def return_metrics(_ignore):
                return self.rate_measurer.get_metrics()
            scenario.addCallback(return_metrics)

            return scenario.addActionFinish()
