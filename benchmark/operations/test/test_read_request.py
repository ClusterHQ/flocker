# Copyright 2015 ClusterHQ Inc.  See LICENSE file for details.
"""
Operations tests for the control service benchmarks.
"""
from uuid import uuid4
from ipaddr import IPAddress

from zope.interface.verify import verifyClass

from twisted.internet.task import Clock
from twisted.python.components import proxyForInterface

from flocker.apiclient import IFlockerAPIV1Client, FakeFlockerClient
from flocker.testtools import TestCase

from benchmark.cluster import BenchmarkCluster
from benchmark._interfaces import IOperation
from benchmark.operations.read_request import ReadRequest


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


class ReadRequestTests(TestCase):
    """
    ReadRequest operation tests.
    """

    def test_implements_IOperation(self):
        """
        ReadRequest provides the IOperation interface.
        """
        verifyClass(IOperation, ReadRequest)

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
            cluster = BenchmarkCluster(
                IPAddress('10.0.0.1'),
                lambda reactor: control_service,
                {},
                None,
            )
            request = ReadRequest(Clock(), cluster, 'list_datasets_state')
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
