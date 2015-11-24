# Copyright 2015 ClusterHQ Inc.  See LICENSE file for details.

from twisted.internet.task import Clock
from twisted.trial.unittest import SynchronousTestCase

from benchmark.operations import Wait


class WaitOperationTests(SynchronousTestCase):
    """
    Test Wait operation
    """

    def test_wait(self):
        """
        Wait operation fires after specified time.
        """
        seconds = 10
        clock = Clock()
        op = Wait(clock=clock, control_service=None, wait_seconds=seconds)
        probe = op.get_probe()
        d = probe.run()
        d.addCallback(lambda ignored: probe.cleanup)
        self.assertNoResult(d)
        # Time passes
        clock.advance(seconds)
        self.successResultOf(d)
