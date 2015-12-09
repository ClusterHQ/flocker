# Copyright 2015 ClusterHQ Inc.  See LICENSE file for details.
"""
Wallclock time metric for the control service benchmarks.
"""

from zope.interface import implementer

from .._interfaces import IMetric


@implementer(IMetric)
class WallClock(object):
    """
    Measure the elapsed wallclock time during an operation.
    """

    def __init__(self, reactor, cluster):
        self.reactor = reactor

    def measure(self, f, *a, **kw):
        def finished(ignored):
            end = self.reactor.seconds()
            elapsed = end - start
            return elapsed

        start = self.reactor.seconds()
        d = f(*a, **kw)
        d.addCallback(finished)
        return d
