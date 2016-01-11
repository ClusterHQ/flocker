# Copyright 2016 ClusterHQ Inc.  See LICENSE file for details.
from itertools import repeat
from uuid import uuid4
from ipaddr import IPAddress

from eliot.testing import capture_logging

from twisted.internet.defer import Deferred, succeed
from twisted.internet.task import Clock
from twisted.python.components import proxyForInterface
from twisted.python.failure import Failure

from flocker.apiclient._client import (
    IFlockerAPIV1Client, FakeFlockerClient, Node
)
from flocker.testtools import TestCase

from benchmark.cluster import BenchmarkCluster
from benchmark.scenarios import (
    write_request_load_scenario, RequestRateTooLow, RequestRateNotReached,
    RequestOverload, DatasetCreationTimeout, RequestScenarioAlreadyStarted,
)

DEFAULT_VOLUME_SIZE = 1073741824


class RequestDroppingFakeFlockerClient(
    proxyForInterface(IFlockerAPIV1Client)
):
    """
    A ``FakeFlockerClient`` that can drop alternating requests.
    """
    def __init__(self, client):
        super(RequestDroppingFakeFlockerClient, self).__init__(client)
        self.drop_requests = False
        self._dropped_last_request = False

    def move_dataset(self, primary, dataset_id, configuration_tag=None):
        if not self.drop_requests:
            return succeed(True)
        else:
            if self._dropped_last_request:
                self._dropped_last_request = False
                return succeed(True)
            self._dropped_last_request = True
        return Deferred()


class FakeNetworkError(Exception):
    """
    A reason for getting no response from a call.
    """


class RequestErrorFakeFlockerClient(
    proxyForInterface(IFlockerAPIV1Client)
):
    """
    A ``FakeFlockerClient`` that can result in failed requests.
    """
    def __init__(self, client, reactor):
        super(RequestErrorFakeFlockerClient, self).__init__(client)
        self.fail_requests = False
        self.reactor = reactor
        self.delay = 1

    def move_dataset(self, primary, dataset_id, configuration_tag=None):
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


class UnresponsiveDatasetCreationFakeFlockerClient(
    proxyForInterface(IFlockerAPIV1Client)
):
    """
    A ``FakeFlockerClient`` that does not respond to requests.
    """
    def __init__(self, client):
        super(
            UnresponsiveDatasetCreationFakeFlockerClient, self
        ).__init__(client)

    def create_dataset(self, primary, maximum_size=None, dataset_id=None,
                       metadata=None, configuration_tag=None):
        return Deferred()


class write_request_load_scenarioTest(TestCase):
    """
    ``write_request_load_scenario`` tests.
    """
    def setUp(self):
        super(write_request_load_scenarioTest, self).setUp()
        self.node1 = Node(uuid=uuid4(), public_address=IPAddress('10.0.0.1'))
        self.node2 = Node(uuid=uuid4(), public_address=IPAddress('10.0.0.2'))

    def make_cluster(self, FlockerClientInstance):
        """
        Create a cluster that can be used by the scenario tests.
        """
        return BenchmarkCluster(
            self.node1.public_address,
            lambda reactor: FlockerClientInstance,
            {self.node1.public_address, self.node2.public_address},
            default_volume_size=DEFAULT_VOLUME_SIZE,
        )

    def get_fake_flocker_client_instance(self):
        """
        Returns a ``FakeFlockerClient`` instance with the nodes
        defined in the init.
        """
        return FakeFlockerClient([self.node1, self.node2])

    def get_dropping_flocker_client_instance(self):
        """
        Returns a ``RequestDroppingFakeFlockerClient`` instance
        using the nodes defined in the init.
        """
        return RequestDroppingFakeFlockerClient(
            self.get_fake_flocker_client_instance())

    def get_unresponsive_flocker_client_instance(self):
        """
        Returns a ``UnresponsiveDatasetCreationFakeFlockerClient``
        instance using the nodes defined in the init.
        """
        return UnresponsiveDatasetCreationFakeFlockerClient(
            self.get_fake_flocker_client_instance())

    def get_error_response_client(self, reactor):
        """
        Returns a ``RequestErrorFakeFlockerClient`` instance using the
        nodes defined in the init.
        """
        return RequestErrorFakeFlockerClient(
            self.get_fake_flocker_client_instance(),
            reactor
        )

    @capture_logging(None)
    def test_setup_generates_dataset(self, _logger):
        """
        ``write_request_load_scenario`` starts and stops without collapsing.
        """
        c = Clock()
        cluster = self.make_cluster(self.get_fake_flocker_client_instance())
        s = write_request_load_scenario(c, cluster, 5, sample_size=3)

        def assert_created(returned_datasets):
            self.assertNotEqual(returned_datasets, [])

        # Create a datasest and verify we get a success
        d = s.scenario_setup._create_dataset(self.node1)
        self.successResultOf(d)

        # Verify that a dataset is actually being created
        d2 = s.scenario_setup.control_service.list_datasets_configuration()
        d2.addCallback(assert_created)
        s.stop()

    def test_setup_retries_generating_dataset(self):
        # XXX: Not implemented. This will just return an error
        # Should we implement it?
        pass

    def test_setup_timeout_when_datasat_not_created(self):
        """
        ``write_request_load_scenario`` should timeout if the setup the dataset
        creation does not complete within the given time.
        """
        c = Clock()
        cluster = self.make_cluster(
            self.get_unresponsive_flocker_client_instance())
        s = write_request_load_scenario(c, cluster, 5, sample_size=3)

        d = s.start()
        c.pump(repeat(1, s.scenario_setup.timeout+1))

        failure = self.failureResultOf(d)
        self.assertIsInstance(failure.value, DatasetCreationTimeout)

    @capture_logging(None)
    def test_write_request_load_succeeds(self, _logger):
        """
        ``write_request_load_scenario`` starts and stops without collapsing.
        """
        c = Clock()
        cluster = self.make_cluster(self.get_fake_flocker_client_instance())
        sample_size = 5
        s = write_request_load_scenario(c, cluster, sample_size=sample_size)

        d = s.start()

        # Request rate samples are recorded every second and we need to
        # collect enough samples to establish the rate which is defined
        # by `sample_size`. Therefore, advance the clock by
        # `sample_size` seconds to obtain enough samples.
        c.pump(repeat(1, sample_size))
        s.maintained().addBoth(lambda x: self.fail())
        d.addCallback(lambda ignored: s.stop())
        self.successResultOf(d)

    @capture_logging(None)
    def test_scenario_succeeds_when_rate_has_tolerated_drop(self, _logger):
        """
        ``write_request_load_scenario`` succeeds even if the rate drops,
        if it is within the tolerance percentage.

        Establish the requested rate by having the ``FakeFlockerClient``
        respond to all requests, then lower the rate by dropping
        alternate requests.
        """
        c = Clock()

        control_service = self.get_dropping_flocker_client_instance()
        cluster = self.make_cluster(control_service)
        sample_size = 5
        s = write_request_load_scenario(c, cluster, sample_size=sample_size,
                                        tolerance_percentage=0.6)
        cluster.get_control_service(c).drop_requests = True
        d = s.start()

        s.maintained().addBoth(lambda x: self.fail())
        d.addCallback(lambda ignored: s.stop())
        # Generate enough samples to finish the scenario
        c.pump(repeat(1, sample_size*s.request_rate))

        self.successResultOf(d)

    @capture_logging(None)
    def test_write_scenario_start_stop_start_succeeds(self, _logger):
        """
        ``write_request_load_scenario`` starts, stops and starts
        without collapsing.
        """
        c = Clock()
        cluster = self.make_cluster(self.get_fake_flocker_client_instance())
        sample_size = 5
        s = write_request_load_scenario(c, cluster, sample_size=sample_size)
        # Start and stop
        s.start()
        c.pump(repeat(1, sample_size))
        s.stop()

        # Start again and check it succeeds.
        d = s.start()
        c.pump(repeat(1, sample_size))
        s.maintained().addBoth(lambda x: self.fail())
        d.addCallback(lambda ignored: s.stop())
        self.successResultOf(d)

    @capture_logging(None)
    def test_scenario_throws_exception_when_already_started(self, _logger):
        """
        start method in the ``RequestLoadScenario`` throws a
        ``RequestScenarioAlreadyStarted`` if the scenario is already started.
        """
        c = Clock()
        cluster = self.make_cluster(self.get_fake_flocker_client_instance())
        sample_size = 5
        s = write_request_load_scenario(c, cluster, sample_size=sample_size)
        # Start and stop
        s.start()
        c.pump(repeat(1, sample_size))
        self.assertRaises(RequestScenarioAlreadyStarted, s.start)

    @capture_logging(None)
    def test_scenario_throws_exception_when_rate_drops(self, _logger):
        """
        ``write_request_load_scenario`` raises ``RequestRateTooLow`` if rate
        drops below the requested rate.

        Establish the requested rate by having the ``FakeFlockerClient``
        respond to all requests, then lower the rate by dropping
        alternate requests. This should result in ``RequestRateTooLow``
        being raised.
        """
        c = Clock()
        control_service = self.get_dropping_flocker_client_instance()
        cluster = self.make_cluster(control_service)
        sample_size = 5
        s = write_request_load_scenario(c, cluster, sample_size=sample_size,
                                        tolerance_percentage=0)

        s.start()

        # Advance the clock by `sample_size` seconds to establish the
        # requested rate.
        c.pump(repeat(1, sample_size))

        control_service.drop_requests = True

        # Advance the clock by 2 seconds so that a request is dropped
        # and a new rate which is below the target can be established.
        c.advance(2)

        failure = self.failureResultOf(s.maintained())
        self.assertIsInstance(failure.value, RequestRateTooLow)

    @capture_logging(None)
    def test_scenario_throws_exception_if_requested_rate_not_reached(
        self, _logger
    ):
        """
        ``write_request_load_scenario`` raises ``RequestRateNotReached`` if
        the target rate cannot be established within a given timeframe.
        """
        c = Clock()
        control_service = self.get_dropping_flocker_client_instance()
        cluster = self.make_cluster(control_service)
        s = write_request_load_scenario(c, cluster)
        control_service.drop_requests = True
        d = s.start()

        # Continue the clock for one second longer than the timeout
        # value to allow the timeout to be triggered.
        c.advance(s.timeout + 1)

        failure = self.failureResultOf(d)
        self.assertIsInstance(failure.value, RequestRateNotReached)

    @capture_logging(None)
    def test_scenario_throws_exception_if_overloaded(self, __logger):
        """
        ``write_request_load_scenario`` raises ``RequestOverload`` if the
        difference between sent requests and received requests exceeds
        the tolerated difference once we start monitoring the scenario.

        Note that, right now, the only way to make it fail is to generate
        this difference before we start monitoring the scenario.
        Once we implement some kind of tolerance, to allow fluctuations
        in the rate, we can update this tests to trigger the exception
        in a more realistic manner.
        """
        # XXX Update this test when we add tolerance for rate fluctuations.
        # See FLOC-3757.
        c = Clock()
        control_service = self.get_dropping_flocker_client_instance()
        cluster = self.make_cluster(control_service)
        target_rate = 10
        sample_size = 20
        s = write_request_load_scenario(
            c, cluster, request_rate=target_rate, sample_size=sample_size
        )
        dropped_rate = target_rate / 2
        seconds_to_overload = s.max_outstanding / dropped_rate

        s.start()
        # Reach initial rate
        control_service.drop_requests = True
        # Initially, we generate enough dropped requests so that the scenario
        # is overloaded when we start monitoring.
        c.pump(repeat(1, seconds_to_overload+1))
        # We stop dropping requests
        control_service.drop_requests = False
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
        ``write_request_load_scenario`` should only be considered as stopped
        when all outstanding requests made by it have completed.
        """
        c = Clock()

        control_service = self.get_error_response_client(c)
        cluster = self.make_cluster(control_service)
        delay = 1

        control_service.delay = delay
        sample_size = 5
        s = write_request_load_scenario(
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
        ``write_request_load_scenario`` should timeout if the outstanding
        requests for the scenarion do not complete within the specified
        time.
        """
        c = Clock()

        control_service = self.get_error_response_client(c)
        cluster = self.make_cluster(control_service)
        sample_size = 5
        s = write_request_load_scenario(
            c, cluster, request_rate=10, sample_size=sample_size
        )

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
