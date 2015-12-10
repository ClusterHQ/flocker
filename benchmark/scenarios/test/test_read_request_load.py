from itertools import repeat
from uuid import uuid4
from ipaddr import IPAddress
import math
from twisted.internet.defer import succeed
from twisted.internet.task import Clock
from twisted.python.components import proxyForInterface
from twisted.trial.unittest import SynchronousTestCase

from flocker.apiclient._client import (
    IFlockerAPIV1Client, FakeFlockerClient, Node
)

from benchmark.scenarios import (
    ReadRequestLoadScenario, RateMeasurer, RequestRateTooLow,
    RequestRateNotReached
)

from benchmark.scenarios.read_request_load import DEFAULT_SAMPLE_SIZE

from benchmark.cluster import BenchmarkCluster


class RateMeasurerTest(SynchronousTestCase):
    """
    RateMeasurer tests
    """

    def test_rate_is_nan_when_no_samples(self):
        """
        """
        r = RateMeasurer(Clock())
        self.assertTrue(math.isnan(r.rate()))

    def test_rate_is_nan_when_not_enough_samples(self):
        """
        """
        c = Clock()
        r = RateMeasurer(c)

        r.new_sample()
        c.advance(1)

        self.assertTrue(math.isnan(r.rate()))

    def test_rate_is_correct_when_enough_samples(self):
        """
        """
        c = Clock()
        sample_size = 2
        r = RateMeasurer(c, sample_size=sample_size)

        # Advance by sample size + 1 because the RateMeasurer only knows
        # that time has passed when new_sample is called.
        for i in xrange(sample_size + 1):
            r.new_sample()
            c.advance(1)

        # TODO: Should this be assertAlmostEqual? Will this pass
        # everywhere? We are suspicious of floating point comparisons
        self.assertEqual(r.rate(), 1.0)

    def test_old_samples_are_not_considered(self):
        """
        """
        c = Clock()
        sample_size = 2
        r = RateMeasurer(c, sample_size=sample_size)

        # Create a rate of 1.0
        for i in xrange(sample_size):
            r.new_sample()
            c.advance(1)

        # Create a rate of 2.0
        for i in xrange(sample_size + 1):
            r.new_sample()
            r.new_sample()
            c.advance(1)

        self.assertEqual(r.rate(), 2.0)


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
        s = ReadRequestLoadScenario(c, cluster, 5, interval=1)

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
        s = ReadRequestLoadScenario(c, cluster, 5, interval=1)

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
        s = ReadRequestLoadScenario(c, cluster, 5, interval=1)

        d = s.start()
        cluster.get_control_service(c).drop_requests = True

        # Continue the clock for one second longer than the timeout
        # value to allow the timeout to be triggered.
        c.pump(repeat(1, s.timeout + 1))

        failure = self.failureResultOf(d)
        self.assertIsInstance(failure.value, RequestRateNotReached)
