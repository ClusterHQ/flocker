# Copyright 2016 ClusterHQ Inc.  See LICENSE file for details.
from itertools import repeat
from uuid import uuid4
from ipaddr import IPAddress

from eliot.testing import capture_logging

from twisted.internet.defer import succeed, Deferred
from twisted.internet.task import Clock
from twisted.python.failure import Failure

from flocker.apiclient._client import FakeFlockerClient, Node
from flocker.testtools import TestCase

from benchmark.cluster import BenchmarkCluster
from benchmark.scenarios import (
    RequestRateTooLow, RequestRateNotReached,
    RequestOverload, read_request_load_scenario, RequestScenarioAlreadyStarted,
)

DEFAULT_VOLUME_SIZE = 1073741824


class RequestDroppingFakeFlockerClient:
    """
    A ``FakeFlockerClient`` that can drop alternating requests.
    """
    def __init__(self, client, reactor):
        self.drop_requests = False
        self._dropped_last_request = False

    # Every attribute access is for a no-arg method.  Return a function
    # that drops every second request if ``drop_requests`` is True.
    def __getattr__(self, name):
        def f():
            if not self.drop_requests:
                return succeed(True)
            else:
                if self._dropped_last_request:
                    self._dropped_last_request = False
                    return succeed(True)
                self._dropped_last_request = True
            return Deferred()
        return f


class FakeNetworkError(Exception):
    """
    A reason for getting no response from a call.
    """


class RequestErrorFakeFlockerClient:
    """
    A ``FakeFlockerClient`` that can result in failed requests.
    """
    def __init__(self, client, reactor):
        self.fail_requests = False
        self.reactor = reactor
        self.delay = 1

    # Every attribute access is for a no-arg method.  Return a function
    # that fails slowly if ``fail_requests`` is True.
    def __getattr__(self, name):
        def f():
            if not self.fail_requests:
                return succeed(True)
            else:
                def fail_later(secs):
                    d = Deferred()
                    self.reactor.callLater(
                        secs, d.errback, Failure(FakeNetworkError())
                    )
                    return d
                return fail_later(self.delay)
        return f


class read_request_load_scenarioTest(TestCase):
    """
    ``read_request_load_scenario`` tests
    """
    def make_cluster(self, make_flocker_client):
        """
        Create a cluster that can be used by the scenario tests.
        """
        node1 = Node(uuid=uuid4(), public_address=IPAddress('10.0.0.1'))
        node2 = Node(uuid=uuid4(), public_address=IPAddress('10.0.0.2'))
        return BenchmarkCluster(
            node1.public_address,
            lambda reactor: make_flocker_client(
                FakeFlockerClient([node1, node2]), reactor
            ),
            {node1.public_address, node2.public_address},
            default_volume_size=DEFAULT_VOLUME_SIZE,
        )

    @capture_logging(None)
    def test_read_request_load_succeeds(self, _logger):
        """
        ``read_request_load_scenario`` starts and stops without collapsing.
        """
        c = Clock()

        node1 = Node(uuid=uuid4(), public_address=IPAddress('10.0.0.1'))
        node2 = Node(uuid=uuid4(), public_address=IPAddress('10.0.0.2'))
        cluster = BenchmarkCluster(
            node1.public_address,
            lambda reactor: FakeFlockerClient([node1, node2]),
            {node1.public_address, node2.public_address},
            default_volume_size=DEFAULT_VOLUME_SIZE
        )

        sample_size = 5
        s = read_request_load_scenario(c, cluster, sample_size=sample_size)

        d = s.start()

        # Request rate samples are recorded every second and we need to
        # collect enough samples to establish the rate which is defined
        # by `sample_size`. Therefore, advance the clock by
        # `sample_size` seconds to obtain enough samples.
        c.pump(repeat(1, sample_size))
        s.maintained().addBoth(lambda x: self.fail())
        d.addCallback(lambda ignored: s.stop())
        c.pump(repeat(1, sample_size))
        self.successResultOf(d)

    @capture_logging(None)
    def test_read_request_load_start_stop_start_succeeds(self, _logger):
        """
        ``read_request_load_scenario`` starts, stops and starts
        without collapsing.
        """
        c = Clock()

        node1 = Node(uuid=uuid4(), public_address=IPAddress('10.0.0.1'))
        node2 = Node(uuid=uuid4(), public_address=IPAddress('10.0.0.2'))
        cluster = BenchmarkCluster(
            node1.public_address,
            lambda reactor: FakeFlockerClient([node1, node2]),
            {node1.public_address, node2.public_address},
            default_volume_size=DEFAULT_VOLUME_SIZE
        )

        sample_size = 5
        s = read_request_load_scenario(c, cluster, sample_size=sample_size)
        # Start and stop
        s.start()
        c.pump(repeat(1, sample_size))
        s.stop()

        # Start again and verify the scenario succeeds
        d = s.start()
        c.pump(repeat(1, sample_size))
        s.maintained().addBoth(lambda x: self.fail())
        d.addCallback(lambda ignored: s.stop())
        c.pump(repeat(1, sample_size))
        self.successResultOf(d)

    @capture_logging(None)
    def test_scenario_throws_exception_when_already_started(self, _logger):
        """
        start method in the ``RequestLoadScenario`` throws a
        ``RequestScenarioAlreadyStarted`` if the scenario is already started.
        """
        c = Clock()

        node1 = Node(uuid=uuid4(), public_address=IPAddress('10.0.0.1'))
        node2 = Node(uuid=uuid4(), public_address=IPAddress('10.0.0.2'))
        cluster = BenchmarkCluster(
            node1.public_address,
            lambda reactor: FakeFlockerClient([node1, node2]),
            {node1.public_address, node2.public_address},
            default_volume_size=DEFAULT_VOLUME_SIZE
        )

        sample_size = 5
        s = read_request_load_scenario(c, cluster, sample_size=sample_size)

        s.start()

        self.assertRaises(RequestScenarioAlreadyStarted, s.start)

    @capture_logging(None)
    def test_scenario_throws_exception_when_rate_drops(self, _logger):
        """
        ``read_request_load_scenario`` raises ``RequestRateTooLow`` if rate
        drops below the requested rate.

        Establish the requested rate by having the ``FakeFlockerClient``
        respond to all requests, then lower the rate by dropping
        alternate requests. This should result in ``RequestRateTooLow``
        being raised.
        """
        c = Clock()

        cluster = self.make_cluster(RequestDroppingFakeFlockerClient)
        sample_size = 5
        s = read_request_load_scenario(c, cluster, sample_size=sample_size,
                                       tolerance_percentage=0)

        s.start()

        # Advance the clock by `sample_size` seconds to establish the
        # requested rate.
        c.pump(repeat(1, sample_size))

        cluster.get_control_service(c).drop_requests = True

        # Advance the clock by 2 seconds so that a request is dropped
        # and a new rate which is below the target can be established.
        c.advance(2)

        failure = self.failureResultOf(s.maintained())
        self.assertIsInstance(failure.value, RequestRateTooLow)

    @capture_logging(None)
    def test_scenario_succeeds_when_rate_has_tolerated_drop(self, _logger):
        """
        ``read_request_load_scenario`` succeeds even if the rate drops,
        if it is within the tolerance percentage.

        Establish the requested rate by having the ``FakeFlockerClient``
        respond to all requests, then lower the rate by dropping
        alternate requests.
        """
        c = Clock()

        cluster = self.make_cluster(RequestDroppingFakeFlockerClient)
        sample_size = 5
        s = read_request_load_scenario(c, cluster, sample_size=sample_size,
                                       tolerance_percentage=0.6)
        cluster.get_control_service(c).drop_requests = True
        d = s.start()
        s.maintained().addBoth(lambda x: self.fail())
        d.addCallback(lambda ignored: s.stop())
        # Generate enough samples to finish the scenario
        c.pump(repeat(1, sample_size*s.request_rate))

        self.successResultOf(d)

    @capture_logging(None)
    def test_scenario_throws_exception_if_requested_rate_not_reached(
        self, _logger
    ):
        """
        ``read_request_load_scenario`` raises ``RequestRateNotReached`` if the
        target rate cannot be established within a given timeframe.
        """
        c = Clock()
        cluster = self.make_cluster(RequestDroppingFakeFlockerClient)
        s = read_request_load_scenario(c, cluster, tolerance_percentage=0)
        cluster.get_control_service(c).drop_requests = True
        d = s.start()

        # Continue the clock for one second longer than the timeout
        # value to allow the timeout to be triggered.
        c.advance(s.timeout + 1)

        failure = self.failureResultOf(d)
        self.assertIsInstance(failure.value, RequestRateNotReached)

    @capture_logging(None)
    def test_scenario_throws_exception_if_overloaded(self, _logger):
        """
        ``read_request_load_scenario`` raises ``RequestOverload`` if the
        difference between sent requests and received requests exceeds
        the tolerated difference once we start monitoring the scenario.

        Note that, right now, the only way to make it fail is to generate
        this difference before we start monitoring the scenario.
        Once we implement some kind of tolerance, to allow fluctuations
        in the rate, we can update this tests to trigger the exception
        in a more realistic manner.
        """
        # XXX Update this test when we add tolerance for rate fluctuations.
        c = Clock()
        cluster = self.make_cluster(RequestDroppingFakeFlockerClient)
        target_rate = 10
        sample_size = 20
        s = read_request_load_scenario(c, cluster, request_rate=target_rate,
                                       sample_size=sample_size)
        dropped_rate = target_rate / 2
        seconds_to_overload = s.max_outstanding / dropped_rate

        s.start()
        # Reach initial rate
        cluster.get_control_service(c).drop_requests = True
        # Initially, we generate enough dropped requests so that the scenario
        # is overloaded when we start monitoring.
        c.pump(repeat(1, seconds_to_overload+1))
        # We stop dropping requests
        cluster.get_control_service(c).drop_requests = False
        # Now we generate the initial rate to start monitoring the scenario
        c.pump(repeat(1, sample_size))
        # We only need to advance one more second (first loop in the monitoring
        # loop) to trigger RequestOverload
        c.advance(1)

        failure = self.failureResultOf(s.maintained())
        self.assertIsInstance(failure.value, RequestOverload)

    @capture_logging(None)
    def test_scenario_stops_only_when_no_outstanding_requests(self, logger):
        """
        ``read_request_load_scenario`` should only be considered as stopped
        when all outstanding requests made by it have completed.
        """
        c = Clock()

        cluster = self.make_cluster(RequestErrorFakeFlockerClient)
        delay = 1

        control_service = cluster.get_control_service(c)

        control_service.delay = delay
        sample_size = 5
        s = read_request_load_scenario(
            c, cluster, request_rate=10, sample_size=sample_size
        )

        d = s.start()
        s.maintained().addBoth(lambda x: self.fail())

        # Advance the clock by `sample_size` seconds to establish the
        # requested rate.
        c.pump(repeat(1, sample_size))

        # Force the control service to fail requests for one second.
        # These requests will fail after the delay period set in the
        # control service.
        control_service.fail_requests = True
        c.advance(1)
        control_service.fail_requests = False

        d.addCallback(lambda ignored: s.stop())

        # The scenario should not successfully stop until after the
        # delay period for the failed requests.
        self.assertNoResult(d)
        c.advance(delay)

        # The scenario requests that failed will have been logged.
        logger.flushTracebacks(FakeNetworkError)

        self.successResultOf(d)

    @capture_logging(None)
    def test_scenario_timeouts_if_requests_not_completed(self, _logger):
        """
        ``read_request_load_scenario`` should timeout if the outstanding
        requests for the scenario do not complete within the specified time.
        """
        c = Clock()

        cluster = self.make_cluster(RequestErrorFakeFlockerClient)
        sample_size = 5
        s = read_request_load_scenario(
            c, cluster, request_rate=10, sample_size=sample_size
        )

        control_service = cluster.get_control_service(c)

        # Set the delay for the requests to be longer than the scenario
        # timeout
        control_service.delay = s.timeout + 10

        d = s.start()
        s.maintained().addBoth(lambda x: self.fail())

        # Advance the clock by `sample_size` seconds to establish the
        # requested rate.
        c.pump(repeat(1, sample_size))

        control_service.fail_requests = True
        c.advance(1)
        control_service.fail_requests = False

        d.addCallback(lambda ignored: s.stop())

        # Advance the clock by the timeout value so it is triggered
        # before the requests complete.
        self.assertNoResult(d)
        c.advance(s.timeout + 1)
        self.assertTrue(s.rate_measurer.outstanding() > 0)
        self.successResultOf(d)
