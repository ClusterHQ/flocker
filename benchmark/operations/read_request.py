from pyrsistent import PClass, field
from zope.interface import implementer

from twisted.internet.defer import succeed
from twisted.web.client import ResponseFailed

from .._interfaces import IProbe, IOperation


@implementer(IProbe)
class ReadRequestProbe(PClass):
    """
    A probe to perform a read request on the control service.
    """

    control_service = field(mandatory=True)

    def run(self):
        d = self.control_service.list_datasets_state()
        return d

    def cleanup(self):
        return succeed(None)


@implementer(IOperation)
class ReadRequest(PClass):
    """
    An operation to perform a read request on the control service.
    """

    # `clock` unused, but required for __init__ signature
    clock = field(mandatory=True)
    control_service = field(mandatory=True)

    def get_probe(self):
        return ReadRequestProbe(control_service=self.control_service)
