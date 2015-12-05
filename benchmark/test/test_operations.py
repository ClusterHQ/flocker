# Copyright 2015 ClusterHQ Inc.  See LICENSE file for details.
"""
Operations tests for the control service benchmarks.
"""
from uuid import uuid4

from zope.interface.verify import verifyObject

from twisted.internet.task import Clock
from twisted.python.components import proxyForInterface
from twisted.trial.unittest import SynchronousTestCase

from flocker.apiclient import IFlockerAPIV1Client, FakeFlockerClient

from benchmark.operations import NoOperation, ReadRequest
from benchmark._interfaces import IProbe, IOperation


def check_interfaces(factory):
    """
    Check interfaces for IOperation/IProbe pairs.

    Check that an IOperation factory produces an IOperation, whose
    ``get_probe`` method creates an IProbe.
    """

    class OperationTests(SynchronousTestCase):

        def test_interfaces(self):
            operation = factory(clock=Clock(), control_service=None)
            verifyObject(IOperation, operation)
            probe = operation.get_probe()
            verifyObject(IProbe, probe)

    testname = '{}InterfaceTests'.format(factory.__name__)
    OperationTests.__name__ = testname
    globals()[testname] = OperationTests

for factory in (NoOperation, ReadRequest):
    check_interfaces(factory)


class FastConvergingFakeFlockerClient(
    proxyForInterface(IFlockerAPIV1Client)
):
    """
    Wrapper for a FakeFlockerClient that converges instantly.
    """

    def create_dataset(self, *a, **kw):
        result = self.original.create_dataset(*a, **kw)
        self.original.synchronize_state()
        return result

    def move_dataset(self, *a, **kw):
        result = self.original.move_dataset(*a, **kw)
        self.original.synchronize_state()
        return result

    def delete_dataset(self, *a, **kw):
        result = self.original.delete_dataset(*a, **kw)
        self.original.synchronize_state()
        return result

    def create_container(self, *a, **kw):
        result = self.original.create_container(*a, **kw)
        self.original.synchronize_state()
        return result

    def delete_container(self, *a, **kw):
        result = self.original.delete_container(*a, **kw)
        self.original.synchronize_state()
        return result


class ReadRequestTests(SynchronousTestCase):
    """
    ReadRequest operation tests.
    """

    def test_read_request(self):
        """
        ReadRequest probe returns the cluster state.
        """
        control_service = FastConvergingFakeFlockerClient(FakeFlockerClient())
        primary = uuid4()

        # Create a single dataset on the cluster
        d = control_service.create_dataset(primary=primary)

        # Get the probe to read the state of the cluster
        def start_read_request(result):
            request = ReadRequest(
                clock=Clock(), control_service=control_service)
            return request.get_probe()
        d.addCallback(start_read_request)

        # Run the probe to read the state of the cluster
        def run_probe(probe):
            def cleanup(result):
                cleaned_up = probe.cleanup()
                cleaned_up.addCallback(lambda _ignored: result)
                return cleaned_up
            d = probe.run()
            d.addCallback(cleanup)
            return d
        d.addCallback(run_probe)

        # Only want to check the primaries of the cluster state
        def filter(states):
            return [state.primary for state in states]
        d.addCallback(filter)

        self.assertEqual(self.successResultOf(d), [primary])
