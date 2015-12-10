from zope.interface import implementer

from twisted.internet.defer import succeed

from flocker.apiclient import IFlockerAPIV1Client

from .._interfaces import IProbe, IOperation


class InvalidMethod(Exception):
    """
    Method not suitable for use with ReadRequest operation.

    The method must be provided by the IFlockerAPIV1Client interface,
    and require no parameters.
    """


def validate_method_name(interface, method_name):
    """
    Check that method name exists in interface and requires no parameters.

    :param zope.interface.Interface interface: Interface to validate against.
    :param str method_name: Method name to validate.
    :raise InvalidMethod: if name is not valid or requires parameters.
    """
    for name, method in interface.namesAndDescriptions():
        if name == method_name:
            if len(method.getSignatureInfo()['required']) > 0:
                raise InvalidMethod('Require no-arg method')
            return
    raise InvalidMethod(
        'Method not found in interface {}'.format(interface.__name__)
    )


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
        validate_method_name(IFlockerAPIV1Client, method)
        self.request = getattr(cluster.get_control_service(reactor), method)

    def get_probe(self):
        return ReadRequestProbe(self.request)
