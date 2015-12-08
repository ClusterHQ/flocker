from itertools import repeat
from uuid import uuid4
from ipaddr import IPAddress
import math
from twisted.internet.task import Clock
from twisted.trial.unittest import SynchronousTestCase

from flocker.apiclient._client import FakeFlockerClient, Node

from benchmark.scenarios import ReadRequestLoadScenario, RateMeasurer


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


class ReadRequestLoadScenarioTest(SynchronousTestCase):
    """
    ReadRequestLoadScenario tests
    """

    def test_read_request_load_happy(self):
        """
        ReadRequestLoadScenario starts and stops without collapsing.
        """
        node1 = Node(uuid=uuid4(), public_address=IPAddress('10.0.0.1'))
        node2 = Node(uuid=uuid4(), public_address=IPAddress('10.0.0.2'))
        c = Clock()
        s = ReadRequestLoadScenario(c, FakeFlockerClient([node1, node2]), 5,
                                    interval=1)

        d = s.start()
        # TODO: Add comment here to explain these numbers
        c.pump(repeat(1, 6))
        s.maintained().addBoth(lambda x: self.fail())
        d.addCallback(lambda ignored: s.stop())
        self.successResultOf(d)
