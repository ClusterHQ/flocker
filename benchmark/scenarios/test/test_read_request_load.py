from itertools import repeat
from uuid import uuid4
from ipaddr import IPAddress
from twisted.internet.defer import succeed, Deferred
from twisted.internet.task import Clock
from twisted.python.components import proxyForInterface
from twisted.python.failure import Failure
from twisted.trial.unittest import SynchronousTestCase

from flocker.apiclient._client import (
    IFlockerAPIV1Client, FakeFlockerClient, Node
)

from benchmark.scenarios import (
    ReadRequestLoadScenario, RateMeasurer, RequestRateTooLow,
    RequestRateNotReached, RequestOverload
)

from benchmark.cluster import BenchmarkCluster


class RateMeasurerTest(SynchronousTestCase):
    """
    RateMeasurer tests
    """

    def send_requests(self, rate_measurer, num_requests, num_samples):
        """
        Helper function that will send the desired number of request.

        :param rate_measurer: The `RateMeasurer` we are testing
        :param num_requests: The number of request we want to send.
        :param num_samples: The number of samples to collect.
        """
        for i in range(num_samples * num_requests):
            rate_measurer.request_sent()

    def receive_requests(self, rate_measurer, num_requests, num_samples):
        """
        Helper function that will receive the desired number of requests.

        :param rate_measurer: The `RateMeasurer` we are testing
        :param num_requests: The number of request we want to receive.
        :param num_samples: The number of samples to collect.
        """
        ignored = ""
        for i in range(num_samples):
            for i in range(num_requests):
                rate_measurer.response_received(ignored)
            rate_measurer.update_rate()

    def failed_requests(self, rate_measurer, num_failures, num_samples):
        """
        Helper function that will result the desired number of response
        failures.

        :param rate_measurer: The `RateMeasurer` we are testing
        :param num_failures: The number of requests we want to fail.
        :param num_samples: The number of samples to collect.
        """
        result = None
        for i in range(num_samples):
            for i in range(num_failures):
                rate_measurer.request_failed(result)
            rate_measurer.update_rate()

    def increase_rate(self, rate_measurer, num_requests, num_samples):
        """
        Helper function that will increase the rate, sending the
        desired number of request, and receiving the same
        amount of them.

        :param rate_measurer: The `RateMeasurer` we are testing
        :param num_requests: The number of request we want to make.
        :param num_samples: The number of samples to collect.
        """
        self.send_requests(rate_measurer, num_requests, num_samples)
        self.receive_requests(rate_measurer, num_requests, num_samples)

    def test_rate_is_zero_when_no_samples(self):
        """
        When no samples have been collected, the rate should be 0.
        """
        r = RateMeasurer()
        self.assertEqual(r.rate(), 0, "Expected initial rate to be zero")

    def test_rate_is_lower_than_target_when_not_enough_samples(self):
        """
        When the number of samples collected is less than the sample
        size, the rate should be lower than `target_rate`.
        """
        r = RateMeasurer()
        target_rate = 5
        num_samples = r.sample_size - 1

        self.increase_rate(r, target_rate, num_samples)

        self.assertTrue(r.rate() < target_rate)

    def test_rate_is_correct_when_enough_samples(self):
        """
        A RateMeasurer should correctly report the rate when enough
        samples have been collected.
        """
        r = RateMeasurer()
        target_rate = 5

        self.increase_rate(r, target_rate, r.sample_size)

        self.assertEqual(target_rate, r.rate())

    def test_old_samples_are_not_considered(self):
        """
        Old samples should be discarded, meaning that only `sample_size`
        number of requests are considered for the rate, and when receiving
        a new sample, the oldest one is discarded.
        """
        r = RateMeasurer()
        target_rate = 5

        # Generate samples that will achieve a high request rate
        self.increase_rate(r, target_rate * 2, r.sample_size)

        # Generate samples to lower the request rate to the target rate
        self.increase_rate(r, target_rate, r.sample_size)

        self.assertEqual(target_rate, r.rate())

    def test_rate_only_considers_received_samples(self):
        """
        The rate should be based on the number of received requests,
        not the number of sent or failed requests.
        """
        r = RateMeasurer()
        send_request_rate = 100
        failed_request_rate = 10
        receive_request_rate = 5

        self.send_requests(r, send_request_rate, r.sample_size)
        self.failed_requests(r, failed_request_rate, r.sample_size)
        self.receive_requests(r, receive_request_rate, r.sample_size)

        self.assertEqual(receive_request_rate, r.rate())

    def test_outstanding_considers_all_responses(self):
        """
        Requests that fail are considered to be completed requests and
        should be included when calculating the number of outstanding
        requests.
        """
        r = RateMeasurer()

        # Send 25 requests
        self.send_requests(r, 5, r.sample_size)

        # Receive successful responses for 20 of those requests
        self.receive_requests(r, 4, r.sample_size)

        # Mark 5 of the requests as failed
        self.failed_requests(r, 1, r.sample_size)

        self.assertEqual(0, r.outstanding())


class RequestDroppingFakeFlockerClient(
    proxyForInterface(IFlockerAPIV1Client)
):
    """
    A FakeFlockerClient that can drop alternating requests.
    """
    def __init__(self, client, reactor):
        super(RequestDroppingFakeFlockerClient, self).__init__(client)
        self.drop_requests = False
        self._dropped_last_request = False

    def list_nodes(self):
        if not self.drop_requests:
            return succeed(True)
        else:
            if self._dropped_last_request:
                self._dropped_last_request = False
                return succeed(True)
            self._dropped_last_request = True
        return Deferred()


class RequestErrorFakeFlockerClient(
    proxyForInterface(IFlockerAPIV1Client)
):
    """
    A FakeFlockerClient that can result in failured requests.
    """
    def __init__(self, client, reactor):
        super(RequestErrorFakeFlockerClient, self).__init__(client)
        self.fail_requests = False
        self.reactor = reactor
        self.delay = 1

    def list_nodes(self):
        if not self.fail_requests:
            return succeed(True)
        else:
            def fail_later(secs):
                d = Deferred()
                self.reactor.callLater(
                    secs, d.errback, Failure(Exception())
                )
                return d
            return fail_later(self.delay)


class ReadRequestLoadScenarioTest(SynchronousTestCase):
    """
    ReadRequestLoadScenario tests
    """
    def make_cluster(self, FlockerClient):
        """
        Create a cluster that can be used by the scenario tests.
        """
        node1 = Node(uuid=uuid4(), public_address=IPAddress('10.0.0.1'))
        node2 = Node(uuid=uuid4(), public_address=IPAddress('10.0.0.2'))
        return BenchmarkCluster(
            node1.public_address,
            lambda reactor: FlockerClient(
                FakeFlockerClient([node1, node2]), reactor
            ),
            {node1.public_address, node2.public_address},
        )

    def test_read_request_load_succeeds(self):
        """
        ReadRequestLoadScenario starts and stops without collapsing.
        """
        c = Clock()

        node1 = Node(uuid=uuid4(), public_address=IPAddress('10.0.0.1'))
        node2 = Node(uuid=uuid4(), public_address=IPAddress('10.0.0.2'))
        cluster = BenchmarkCluster(
            node1.public_address,
            lambda reactor: FakeFlockerClient([node1, node2]),
            {node1.public_address, node2.public_address},
        )

        sample_size = 5
        s = ReadRequestLoadScenario(c, cluster, sample_size=sample_size)

        d = s.start()

        # Request rate samples are recorded every second and we need to
        # collect enough samples to establish the rate which is defined
        # by `sample_size`. Therefore, advance the clock by
        # `sample_size` seconds to obtain enough samples.
        c.pump(repeat(1, sample_size))
        s.maintained().addBoth(lambda x: self.fail())
        d.addCallback(lambda ignored: s.stop())
        self.successResultOf(d)

    def test_scenario_throws_exception_when_rate_drops(self):
        """
        ReadRequestLoadScenario raises RequestRateTooLow if rate
        drops below the requested rate.

        Establish the requested rate by having the FakeFlockerClient
        respond to all requests, then lower the rate by dropping
        alternate requests. This should result in RequestRateTooLow
        being raised.
        """
        c = Clock()

        cluster = self.make_cluster(RequestDroppingFakeFlockerClient)
        sample_size = 5
        s = ReadRequestLoadScenario(c, cluster, sample_size=sample_size)

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

    def test_scenario_throws_exception_if_requested_rate_not_reached(self):
        """
        ReadRequestLoadScenario raises RequestRateNotReached if the
        target rate cannot be established within a given timeframe.
        """
        c = Clock()
        cluster = self.make_cluster(RequestDroppingFakeFlockerClient)
        s = ReadRequestLoadScenario(c, cluster)
        cluster.get_control_service(c).drop_requests = True
        d = s.start()

        # Continue the clock for one second longer than the timeout
        # value to allow the timeout to be triggered.
        c.advance(s.timeout + 1)

        failure = self.failureResultOf(d)
        self.assertIsInstance(failure.value, RequestRateNotReached)

    def test_scenario_throws_exception_if_overloaded(self):
        """
        `ReadRequestLoadScenario` raises `RequestOverload` if the
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
        s = ReadRequestLoadScenario(c, cluster, request_rate=target_rate,
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

    def test_scenario_stops_only_when_no_outstanding_requests(self):
        """
        `ReadRequestLoadScenario` should only be considered as stopped
        when all outstanding requests made by it have completed.
        """
        c = Clock()

        cluster = self.make_cluster(RequestErrorFakeFlockerClient)
        delay = 1

        cluster.get_control_service(c).delay = delay
        sample_size = 5
        s = ReadRequestLoadScenario(
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
        cluster.get_control_service(c).fail_requests = True
        c.advance(1)
        cluster.get_control_service(c).fail_requests = False

        d.addCallback(lambda ignored: s.stop())

        # The scenario should not successfully stop until after the
        # delay period for the failed requests.
        self.assertNoResult(d)
        c.advance(delay)
        self.successResultOf(d)

    def test_scenario_timeouts_if_requests_not_completed(self):
        """
        `ReadRequestLoadScenario` should timeout if the outstanding
        requests for the scenarion do not complete within the specified
        time.
        """
        c = Clock()

        cluster = self.make_cluster(RequestErrorFakeFlockerClient)
        sample_size = 5
        s = ReadRequestLoadScenario(
            c, cluster, request_rate=10, sample_size=sample_size
        )

        # Set the delay for the requests to be longer than the scenario
        # timeout
        cluster.get_control_service(c).delay = s.timeout + 10

        d = s.start()
        s.maintained().addBoth(lambda x: self.fail())

        # Advance the clock by `sample_size` seconds to establish the
        # requested rate.
        c.pump(repeat(1, sample_size))

        cluster.get_control_service(c).fail_requests = True
        c.advance(1)
        cluster.get_control_service(c).fail_requests = False

        d.addCallback(lambda ignored: s.stop())

        # Advance the clock by the timeout value so it is triggered
        # before the requests complete.
        self.assertNoResult(d)
        c.advance(s.timeout + 1)
        self.assertTrue(s.rate_measurer.outstanding() > 0)
        self.successResultOf(d)
