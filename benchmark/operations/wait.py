# Copyright 2015 ClusterHQ Inc.  See LICENSE file for details.
"""
Wait operation for the control service benchmarks.
"""

from zope.interface import implementer

from twisted.internet.defer import Deferred, succeed

from benchmark._interfaces import IProbe, IOperation


@implementer(IProbe)
class WaitProbe(object):
    """
    A probe to wait for a specified time period.
    """

    def __init__(self, clock, wait_seconds):
        self.clock = clock
        self.wait_seconds = wait_seconds

    def run(self):
        d = Deferred()
        self.clock.callLater(self.wait_seconds, d.callback, None)
        return d

    def cleanup(self):
        return succeed(None)


@implementer(IOperation)
class Wait(object):
    """
    An operation to wait 10 seconds.
    """

    def __init__(self, clock, control_service, wait_seconds=10):
        self.clock = clock
        self.control_service = control_service
        self.wait_seconds = wait_seconds

    def get_probe(self):
        return WaitProbe(clock=self.clock, wait_seconds=self.wait_seconds)
