from zope.interface import implementer

from twisted.internet.defer import succeed

from .._interfaces import IProbe, IOperation


@implementer(IProbe)
class ReadRequestProbe(object):
    """
    A probe to perform a read request on the control service.
    """

    def __init__(self, control_service):
        self.control_service = control_service

    def run(self):
        d = self.control_service.list_datasets_state()
        return d

    def cleanup(self):
        return succeed(None)


@implementer(IOperation)
class ReadRequest(object):
    """
    An operation to perform a read request on the control service.
    """

    def __init__(self, clock, control_service):
        self.clock = clock
        self.control_service = control_service

    def get_probe(self):
        return ReadRequestProbe(control_service=self.control_service)
