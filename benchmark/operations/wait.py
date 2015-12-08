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

    def __init__(self, reactor, wait_seconds):
        self.reactor = reactor
        self.wait_seconds = wait_seconds

    def run(self):
        d = Deferred()
        self.reactor.callLater(self.wait_seconds, d.callback, None)
        return d

    def cleanup(self):
        return succeed(None)


@implementer(IOperation)
class Wait(object):
    """
    An operation to wait for a number of seconds.
    """

    def __init__(self, reactor, cluster, wait_seconds=10):
        self.reactor = reactor
        self.wait_seconds = wait_seconds

    def get_probe(self):
        return WaitProbe(self.reactor, self.wait_seconds)
