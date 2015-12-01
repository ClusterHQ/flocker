from zope.interface import implementer

from twisted.internet.defer import succeed

from .._interfaces import IProbe, IOperation


@implementer(IProbe)
class NoOpProbe(object):
    """
    A probe that performs no operation.
    """

    def run(self):
        return succeed(None)

    def cleanup(self):
        return succeed(None)


@implementer(IOperation)
class NoOperation(object):
    """
    A no-op operation.
    """

    def __init__(self, clock, control_service):
        self.clock = clock
        self.control_service = control_service

    def get_probe(self):
        return NoOpProbe()
