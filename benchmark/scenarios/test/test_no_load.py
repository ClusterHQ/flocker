from zope.interface.verify import verifyObject

from twisted.internet.task import Clock

from flocker.testtools import TestCase
from benchmark.scenarios import NoLoadScenario

from benchmark._interfaces import IScenario


def check_interfaces(factory):
    """
    Check interface for IScenario implementation.
    """

    class ScenarioTests(TestCase):

        def test_interfaces(self):
            scenario = factory(Clock(), None)
            verifyObject(IScenario, scenario)

    testname = '{}InterfaceTests'.format(factory.__name__)
    ScenarioTests.__name__ = testname
    globals()[testname] = ScenarioTests

for factory in (NoLoadScenario,):
    check_interfaces(factory)


class NoLoadScenarioTests(TestCase):
    """
    NoLoadScenario tests
    """

    # XXX: FLOC-3755: This isn't a test since it doesn't start with "test_".
    # It never runs. If this is fixed so that it runs, it fails.
    def no_load_happy(self):
        """
        NoLoadScenario starts and stops without collapsing.
        """
        s = NoLoadScenario(Clock(), None)
        d = s.start()
        s.maintained().addBoth(lambda x: self.fail())
        d.addCallback(s.stop)
        self.successResultOf(d)
