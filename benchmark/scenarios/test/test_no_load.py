from zope.interface.verify import verifyClass

from twisted.internet.task import Clock

from flocker.testtools import TestCase
from benchmark.scenarios import NoLoadScenario

from benchmark._interfaces import IScenario


class NoLoadScenarioTests(TestCase):
    """
    NoLoadScenario tests
    """

    def test_implements_IScenario(self):
        """
        NoLoadScenario provides the IScenario interface.
        """
        verifyClass(IScenario, NoLoadScenario)

    def test_no_load_happy(self):
        """
        NoLoadScenario starts and stops without collapsing.
        """
        s = NoLoadScenario(Clock(), None)
        d = s.start()
        s.maintained().addBoth(lambda x: self.fail())
        d.addCallback(lambda _ignore: s.stop())
        self.successResultOf(d)
