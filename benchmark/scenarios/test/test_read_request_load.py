from itertools import repeat
from uuid import uuid4
from ipaddr import IPAddress
from twisted.internet.defer import succeed, Deferred
from twisted.internet.task import Clock
from twisted.python.components import proxyForInterface
from twisted.trial.unittest import SynchronousTestCase

from flocker.apiclient._client import (
    IFlockerAPIV1Client, FakeFlockerClient, Node
)

from benchmark.scenarios import (
    ReadRequestLoadScenario, RateMeasurer, RequestRateTooLow,
    RequestRateNotReached, RequestOverload
)

from benchmark.scenarios.read_request_load import DEFAULT_SAMPLE_SIZE

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
            rate_measurer.send_request()

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
                rate_measurer.receive_request(ignored)
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

    def test_only_received_samples_considered(self):
        """
        The rate should be based on the number of received requests,
        not the number of sent requests.
        """
        r = RateMeasurer()
        send_request_rate = 100
        receive_request_rate = 5

        self.send_requests(r, send_request_rate, r.sample_size)
        self.receive_requests(r, receive_request_rate, r.sample_size)

        self.assertEqual(receive_request_rate, r.rate())


class RequestDroppingFakeFlockerClient(
    proxyForInterface(IFlockerAPIV1Client)
):
    """
    A FakeFlockerClient that can drop alternating requests.
    """
    def __init__(self, nodes):
        super(RequestDroppingFakeFlockerClient, self).__init__(nodes)
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
            lambda reactor: FlockerClient(FakeFlockerClient([node1, node2])),
            {node1.public_address, node2.public_address},
        )

    def test_read_request_load_succeeds(self):
        """
        ReadRequestLoadScenario starts and stops without collapsing.
        """
        c = Clock()
        cluster = self.make_cluster(FakeFlockerClient)
        s = ReadRequestLoadScenario(c, cluster, 5, sample_size=3)

        d = s.start()

        # Request rate samples are taken at most every second and by
        # default, 5 samples are required to establish the rate.
        # The sample recorded at nth second is the sample for the
        # (n - 1)th second, therefore we need to advance the clock by
        # n + 1 seconds to obtain a rate for n samples.
        c.pump(repeat(1, DEFAULT_SAMPLE_SIZE + 1))
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
        s = ReadRequestLoadScenario(c, cluster, 5, sample_size=1)

        s.start()

        # Advance the clock by DEFAULT_SAMPLE_SIZE + 1 seconds to
        # establish the requested rate.
        c.pump(repeat(1, DEFAULT_SAMPLE_SIZE + 1))

        cluster.get_control_service(c).drop_requests = True

        # Advance the clock by 3 seconds so that a request is dropped
        # and a new rate which is below the target can be established.
        c.pump(repeat(1, 3))

        failure = self.failureResultOf(s.maintained())
        self.assertIsInstance(failure.value, RequestRateTooLow)

    def test_scenario_throws_exception_if_requested_rate_not_reached(self):
        """
        ReadRequestLoadScenario raises RequestRateNotReached if the
        target rate cannot be established within a given timeframe.
        """
        c = Clock()
        cluster = self.make_cluster(RequestDroppingFakeFlockerClient)
        s = ReadRequestLoadScenario(c, cluster, 5, sample_size=1)
        cluster.get_control_service(c).drop_requests = True
        d = s.start()

        # Continue the clock for one second longer than the timeout
        # value to allow the timeout to be triggered.
        c.pump(repeat(1, s.timeout + 1))

        failure = self.failureResultOf(d)
        self.assertIsInstance(failure.value, RequestRateNotReached)

    def test_scenario_throws_exception_if_overloaded(self):
        """
        `ReadRequestLoadScenarioTest` raises `RequestOverload` if,
        once we start monitoring the scenario, we go over the max
        tolerated difference between sent requests and received requests.

        Note that, right now, the only way to make it fail is to generate
        this difference before we start monitoring the scenario.
        Once we implement some kind of tolerance, to allow fluctuations
        in the rate, we can update this tests to trigger the exception
        in a more realistic manner.
        """
        # XXX Update this test when we add tolerance for rate fluctuations.
        c = Clock()
        cluster = self.make_cluster(RequestDroppingFakeFlockerClient)
        req_per_second = 2
        sample_size = 20
        s = ReadRequestLoadScenario(c, cluster, req_per_second,
                                    sample_size=sample_size)
        dropped_req_per_sec = req_per_second / 2
        seconds_to_overload = s.max_outstanding / dropped_req_per_sec

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
        c.pump(repeat(1, 1))

        failure = self.failureResultOf(s.maintained())
        self.assertIsInstance(failure.value, RequestOverload)
