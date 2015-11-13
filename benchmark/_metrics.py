# Copyright 2015 ClusterHQ Inc.  See LICENSE file for details.
"""
Metrics for the control service benchmarks.
"""

from pyrsistent import PClass, field


class _WallClock(PClass):
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


_metrics = {
    'wallclock': _WallClock,
}

supported_metrics = _metrics.keys()
default_metric = 'wallclock'


def get_metric(name):
    return _metrics[name]
