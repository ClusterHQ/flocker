# Copyright 2015 ClusterHQ Inc.  See LICENSE file for details.
"""
Measurement tests for the control service benchmarks.
"""

from twisted.trial.unittest import TestCase
from twisted.internet.task import Clock
from twisted.internet.defer import maybeDeferred

from benchmark._metrics import _WallClock


class WallClockTests(TestCase):

    def test_wallclock(self):
        """
        Returns the difference in time from before and after call to
        function.
        """
        clock = Clock()
        wallclock = _WallClock(clock=clock)
        d = wallclock.measure(maybeDeferred, clock.advance, 1.23)
        d.addCallback(self.assertEqual, 1.23)
