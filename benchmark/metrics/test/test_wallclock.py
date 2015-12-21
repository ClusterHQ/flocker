# Copyright 2015 ClusterHQ Inc.  See LICENSE file for details.
"""
Wallclock metric tests for the control service benchmarks.
"""

from twisted.trial.unittest import SynchronousTestCase
from twisted.internet.task import Clock
from twisted.internet.defer import maybeDeferred

from benchmark.metrics import WallClock


# XXX FLOC-3281 Change to flocker.testtools.TestCase after FLOC-3077 is merged
class WallClockTests(SynchronousTestCase):

    def test_wallclock(self):
        """
        Returns the difference in time from before and after call to
        function.
        """
        clock = Clock()
        wallclock = WallClock(clock, None)
        d = wallclock.measure(maybeDeferred, clock.advance, 1.23)
        self.assertEqual(self.successResultOf(d), 1.23)
