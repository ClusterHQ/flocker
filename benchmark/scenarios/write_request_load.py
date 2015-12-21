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

# XXX make it a common class for Read and Write scenarios.
# Note that the docstrings are not up-to-date because they are being updated
# in the Read scenario
class WRateMeasurer(object):
    """
    Measures the rate of requests in requests per second.

    :ivar sample_size: The number of samples to collect.
    """

    def __init__(self, sample_size=DEFAULT_SAMPLE_SIZE):
        self.sample_size = sample_size
        self._counts = deque([0] * sample_size, sample_size)
        self._sent = 0
        self._received = 0
        self._errors = 0
        self._rate = 0

    def request_sent(self):
        """
        Increase the number of sent requests.
        """
        self._sent += 1

    def response_received(self, ignored):
        """
        Increase the number of received requests.

        :param ignored: The result of a callback. This parameter is
            not used.
        """
        self._received += 1

    def request_failed(self, ignored):
        """
        Increase the error count for failed requests.

        :param ignored: The result of a callback. This parameter is
            not used.
        """
        self._errors += 1

    def update_rate(self):
        """
        Update the current rate and record a new sample.
        """
        self._rate = (
            (self._received - self._counts[0]) / float(self.sample_size)
        )
        self._counts.append(self._received)

    def outstanding(self):
        """
        Return the number of outstanding requests.
        """
        return self._sent - self._received - self._errors

    def rate(self):
        return self._rate


# XXX make this excetions common for read and write scenarios and remove
# the initial W preceding the name
class WRequestRateTooLow(Exception):
    """
    The RequestRate dropped below a threshold.
    """


class WRequestRateNotReached(Exception):
    """
    The RequestRate did not reach the target level.
    """


class WRequestOverload(Exception):
    """
    There are too many outstanding request.
    """

class WDataseCreationTimeout(Exception):
    """
    The dataset could not be created.
    """

class WNoNodesFound(Exception):
    """
    No existent nodes were found.
    """

@implementer(IScenario)
class WriteRequestLoadScenario(object):
    """
    A scenario that places load on the cluster by performing write
    requests at a specified rate.

    :ivar reactor: reactor we are using.
    :ivar cluster: `BenchmarkCluster` containing the control service.
    :ivar request_rate: number requests per second do we want.
    :ivar interval: number of samples we want.
    :ivar timeout: how long we want to wait to reach the requested load
        before timing out.

    """

    def __init__(
        self, reactor, cluster, request_rate=10,
        sample_size=DEFAULT_SAMPLE_SIZE, timeout=45
    ):
        self._maintained = Deferred()
        self.reactor = reactor
        self.control_service = cluster.get_control_service(reactor)
        self.request_rate = request_rate
        self.timeout = timeout
        self.rate_measurer = WRateMeasurer(sample_size)
        self.max_outstanding = 10 * request_rate
        self._dataset_id = ""
        # Send requests per second
        self.loop = LoopingCall.withCount(self._request_and_measure)
        self.loop.clock = self.reactor
        # Once the expected rate is reached, we will start monitoring the scenario
        # inside this loop
        self.monitor_loop = LoopingCall(self.check_rate)
        self.monitor_loop.clock = self.reactor

    def start(self):
        """
        Executes the setup and starts running the write scenario.

        :return: A Deferred that fires when the desired scenario is
            established (e.g. that a certain load is being applied).
        """
        # List all the nodes registered in the control service
        d = self.control_service.list_nodes()
        d.addCallback(self._get_dataset_node)
        # Once we have the list of nodes, we will create a dataset.
        # We cannot start the scenario until we have a working dataset, so
        # `_create_dataset` will work like a setup of the write scenario
        d.addCallback(self._create_dataset)
        # Once we have setup all we need, we can start running the scenario
        d.addCallback(self.run_scenario)
        return d

    def _create_dataset(self, node):
        """
        Creates a dataset in the node given.

        :param node: node where we want the dataset.

        :return: A Deferred that fires when the dataset has been created.

        :raises: `WDataseCreationTimeout` if the creation goes wrong.
        """
        creating = self.control_service.create_dataset(
            primary=node.uuid)
        # Not sure about handling errors and timeout in the same errback.
        # How could I handle them differently?
        def handle_timeout_and_errors(failure):
            failure.trap(CancelledError)
            raise WDataseCreationTimeout()

        timeout(self.reactor, creating, self.timeout)

        creating.addErrback(handle_timeout_and_errors)
        return creating

    def _get_dataset_node(self, nodes):
        """
        Selects the node where the dataset will be created.

        :param nodes: list of `Node` where we will chose one
            to create the dataset.

        :return: the selected `Node`.
        :raise: `WNoNodesFound` if the given list of nodes was empty.
        """
        if not nodes:
           raise WNoNodesFound()
        return nodes[0]


    def _request_and_measure(self, count):
        """
        Updates the rate with the current value and sends `request_rate`
        number of new requests.

        :param count: the number of seconds passed since the last time
            `_request_and_measure` was called.
        """
        for i in range(count):
            self.rate_measurer.update_rate()
        for i in range(self.request_rate):
            d = self.control_service.move_dataset(self.dataset_id,
                                                  self.dataset_id)
            self.rate_measurer.request_sent()
            d.addCallbacks(self.rate_measurer.response_received,
                           errback=eliot.write_failure)

    def check_rate(self):
        """
        Meassures rate and verifies that the rate haven't decreased
        and that the scenario is not overloaded - an scenario would be
        overloaded if there were too many outstanding requests.

        :raise: `RequestRateTooLow` if the rate has dropped.
        :raise: `RequestOverload` if the scenario is overloaded.
        """
        rate = self.rate_measurer.rate()
        if rate < self.request_rate:
            self._fail(WRequestRateTooLow(rate))

        if self.rate_measurer.outstanding() > self.max_outstanding:
            self._fail(WRequestOverload())

    def run_scenario(self, dataset):
        """
        :param dataset `Dataset` we will use to run the write scenario
        :return: A D`eferred` that fires when the desired scenario is
            established (e.g. that a certain load is being applied).
        """
        # The fist thing we need to do before actually running the scenario
        # is to update the dataset_id, as we need the information to do the
        # write requests to generate the load
        self.dataset_id = dataset.dataset_id

        self.loop.start(interval=1)

        def reached_target_rate():
            return self.rate_measurer.rate() >= self.request_rate

        def handle_timeout(failure):
            failure.trap(CancelledError)
            raise WRequestRateNotReached

        # Loop until we reach the expected rate, or we timeout
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
        :return: A `Deferred` that fires with an errback if the desired
            scenario fails to hold between being established and being
            stopped.  This Deferred never fires with a callback.
        """
        return self._maintained

    def _fail(self, exception):
        """
        Fail the scenario. Stops the monitor loop and throws the
        error.

        :param exception: exception that caused the failure.
        """
        self.monitor_loop.stop()
        self._maintained.errback(exception)

    def stop(self):
        """
        Stop the scenario from being maintained, stopping all the loops
        that may be executing.

        :return: A `Deferred` that fires when the desired scenario is
            stopped.
        """
        if self.monitor_loop.running:
            self.monitor_loop.stop()

        if self.loop.running:
            self.loop.stop()

        return succeed(None)

