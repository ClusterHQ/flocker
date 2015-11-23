# Copyright 2015 ClusterHQ Inc.  See LICENSE file for details.
"""
Wait operation for the control service benchmarks.
"""

from pyrsistent import PClass, field
from zope.interface import implementer

from twisted.internet.defer import Deferred, succeed

from benchmark._interfaces import IProbe, IOperation


@implementer(IProbe)
class WaitProbe(PClass):
    """
    A probe to wait for a specified time period.
    """

    clock = field(mandatory=True)
    wait_seconds = field(mandatory=True)

    def run(self):
        d = Deferred()
        self.clock.callLater(self.wait_seconds, d.callback, None)
        return d

    def cleanup(self):
        return succeed(None)


@implementer(IOperation)
class Wait(PClass):
    """
    An operation to wait 10 seconds.
    """

    clock = field(mandatory=True)
    # `control_service` attribute unused, but required for __init__ signature
    control_service = field(mandatory=True)
    wait_seconds = field(initial=10)

    def get_probe(self):
        return WaitProbe(clock=self.clock, wait_seconds=self.wait_seconds)
