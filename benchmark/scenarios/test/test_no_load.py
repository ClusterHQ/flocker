from zope.interface.verify import verifyObject

from twisted.internet.task import Clock
from twisted.trial.unittest import SynchronousTestCase

from benchmark.scenarios import NoLoadScenario

from benchmark._interfaces import IScenario


def check_interfaces(factory):
    """
    Check interface for IScenario implementation.
    """

    class ScenarioTests(SynchronousTestCase):

        def test_interfaces(self):
            scenario = factory(Clock(), None)
            verifyObject(IScenario, scenario)

    testname = '{}InterfaceTests'.format(factory.__name__)
    ScenarioTests.__name__ = testname
    globals()[testname] = ScenarioTests

for factory in (NoLoadScenario,):
    check_interfaces(factory)


class NoLoadScenarioTests(SynchronousTestCase):
    """
    NoLoadScenario tests
    """

    def no_load_happy(self):
        """
        NoLoadScenario starts and stops without collapsing.
        """
        s = NoLoadScenario(Clock(), None)
        d = s.start()
        s.maintained().addBoth(lambda x: self.fail())
        d.addCallback(s.stop)
        self.successResultOf(d)
