# Copyright 2015 ClusterHQ Inc.  See LICENSE file for details.
"""
Metrics for the control service benchmarks.
"""

from pyrsistent import PClass, field
from zope.interface import implementer

from .._interfaces import IMetric


@implementer(IMetric)
class WallClock(PClass):
    """
    Measure the elapsed wallclock time during an operation.
    """
    clock = field(mandatory=True)
    control_service = field()

    def measure(self, f, *a, **kw):
        def finished(ignored):
            end = self.clock.seconds()
            elapsed = end - start
            return elapsed

        start = self.clock.seconds()
        d = f(*a, **kw)
        d.addCallback(finished)
        return d
