# Copyright 2015 ClusterHQ Inc.  See LICENSE file for details.
"""
Measurements for the control service benchmarks.
"""

from pyrsistent import PClass, field

from twisted.internet.defer import maybeDeferred


class _WallClock(PClass):
    """
    Measure the elapsed wallclock time during an operation.
    """
    clock = field(mandatory=True)
    client = field()

    def __call__(self, f, *a, **kw):
        def finished(ignored):
            end = self.clock.seconds()
            elapsed = end - start
            return elapsed

        start = self.clock.seconds()
        d = f(*a, **kw)
        d.addCallback(finished)
        return d


_measurements = {
    'wallclock': _WallClock,
}

supported_measurements = _measurements.keys()
default_measurement = 'wallclock'


def get_measurement(clock, client, name):
    return maybeDeferred(_measurements[name], clock=clock, client=client)
