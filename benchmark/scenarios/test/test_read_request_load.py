from itertools import repeat
from uuid import uuid4
from ipaddr import IPAddress
from twisted.internet.task import Clock
from twisted.trial.unittest import SynchronousTestCase

from flocker.apiclient._client import FakeFlockerClient, Node

from benchmark.scenarios import ReadRequestLoadScenario


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
        s = ReadRequestLoadScenario(c, FakeFlockerClient([node1, node2]), 5, interval=1)

        d = s.start()
        # TODO: Add comment here to explain these numbers
        c.pump(repeat(1, 6))
        s.maintained().addBoth(lambda x: self.fail())
        d.addCallback(lambda ignored: s.stop())
        self.successResultOf(d)
