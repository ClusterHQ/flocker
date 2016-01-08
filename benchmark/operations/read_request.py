from zope.interface import implementer

from twisted.internet.defer import succeed

from flocker.apiclient import IFlockerAPIV1Client

from .._interfaces import IProbe, IOperation
from .._method import validate_no_arg_method


@implementer(IProbe)
class ReadRequestProbe(object):
    """
    A probe to perform a read request on the control service.
    """

    def __init__(self, request):
        self.request = request

    def run(self):
        return self.request()

    def cleanup(self):
        return succeed(None)


@implementer(IOperation)
class ReadRequest(object):
    """
    An operation to perform a read request on the control service.
    """

    def __init__(self, reactor, cluster, method='version'):
        validate_no_arg_method(IFlockerAPIV1Client, method)
        self.request = getattr(cluster.get_control_service(reactor), method)

    def get_probe(self):
        return ReadRequestProbe(self.request)
