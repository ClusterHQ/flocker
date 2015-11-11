from twisted.trial.unittest import TestCase
from twisted.internet.task import Clock
from twisted.internet.defer import maybeDeferred

from benchmark.benchmark_measurements import _WallClock


class WallClockTests(TestCase):

    def test_wallclock(self):
        """
        Returns the difference in time from before and after call to
        function.
        """
        clock = Clock()
        wallclock = _WallClock(clock=clock)
        d = wallclock(maybeDeferred, clock.advance, 1.23)
        d.addCallback(self.assertEqual, 1.23)
