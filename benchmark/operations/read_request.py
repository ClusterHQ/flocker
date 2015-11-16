from pyrsistent import PClass, field
from zope.interface import implementer

from twisted.internet.defer import succeed
from twisted.web.client import ResponseFailed

from .._interfaces import IProbe, IOperation


def _report_error(failure):
    failure.trap(ResponseFailed)
    for reason in failure.value.reasons:
        reason.printTraceback()
    return reason


@implementer(IProbe)
class ReadRequestProbe(PClass):
    """
    A probe to perform a read request on the control service.
    """

    control_service = field(mandatory=True)

    def run(self):
        d = self.control_service.list_datasets_state()
        d.addErrback(_report_error)
        return d

    def cleanup(self):
        return succeed(None)


@implementer(IOperation)
class ReadRequest(PClass):
    """
    An operation to perform a read request on the control service.
    """

    control_service = field(mandatory=True)

    def get_probe(self):
        return ReadRequestProbe(control_service=self.control_service)
