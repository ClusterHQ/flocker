# Copyright 2015 ClusterHQ Inc.  See LICENSE file for details.
"""
Operations for the control service benchmarks.
"""

from pyrsistent import PClass, field
from zope.interface import Interface, implementer

from twisted.internet.defer import succeed
from twisted.web.client import ResponseFailed


class IProbe(Interface):
    """A probe that performs an operation."""

    def run():
        """
        Run the operation.  This should run with as little overhead as
        possible, in order to ensure benchmark measurements are accurate.

        :return: A Deferred firing with the result of the operation.
        """

    def cleanup():
        """
        Perform any cleanup required after the operation.  This is performed
        outside the benchmark measurement.

        :return: A Deferred firing when the cleanup is finished.
        """


class IOperation(Interface):
    """An operation that can be performed."""

    def get_probe():
        """
        Get a probe for the operation. To ensure sequential operations
        perform real work, the operation may return a different
        probe each time.
        """


def _report_error(failure):
    failure.trap(ResponseFailed)
    for reason in failure.value.reasons:
        reason.printTraceback()
    return reason


@implementer(IProbe)
class _NoOpRequest(PClass):
    """
    A probe that performs no operation.
    """

    def run(self):
        return succeed(None)

    def cleanup(self):
        return succeed(None)


@implementer(IOperation)
class _NoOperation(PClass):
    """
    An nop operation.
    """

    control_service = field(mandatory=True)

    def get_probe(self):
        return _NoOpRequest()


@implementer(IProbe)
class _ReadRequest(PClass):
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
class _ReadRequestOperation(PClass):
    """
    An operation to perform a read request on the control service.
    """

    control_service = field(mandatory=True)

    def get_probe(self):
        return _ReadRequest(control_service=self.control_service)


_operations = {
    'nop': _NoOperation,
    'read-request': _ReadRequestOperation,
}

supported_operations = _operations.keys()
default_operation = 'read-request'


def get_operation(name):
    return _operations[name]
