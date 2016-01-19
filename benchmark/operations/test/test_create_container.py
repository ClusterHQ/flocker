# Copyright 2016 ClusterHQ Inc.  See LICENSE file for details.
"""
Create Container operation tests for the control service benchmarks.
"""
from uuid import uuid4

from eliot.testing import capture_logging
from ipaddr import IPAddress
from zope.interface.verify import verifyClass

from twisted.internet.task import Clock

from flocker.apiclient import FakeFlockerClient, Node
from flocker.testtools import TestCase

from benchmark.cluster import BenchmarkCluster
from benchmark._interfaces import IOperation, IProbe
from benchmark.operations.create_container import (
    CreateContainer, CreateContainerProbe, DEFAULT_TIMEOUT,
)
from benchmark.operations._common import EmptyClusterError


class CreateContainerTests(TestCase):
    """
    CreateContainer operation tests.
    """

    def test_implements_IOperation(self):
        """
        CreateContainer provides the IOperation interface.
        """
        verifyClass(IOperation, CreateContainer)

    def test_implements_IProbe(self):
        """
        CreateContainerProbe provides the IProbe interface.
        """
        verifyClass(IProbe, CreateContainerProbe)

    @capture_logging(None)
    def test_create_container(self, _logger):
        """
        CreateContainer probe waits for cluster to converge.
        """
        clock = Clock()

        node_id = uuid4()
        node = Node(uuid=node_id, public_address=IPAddress('10.0.0.1'))
        control_service = FakeFlockerClient([node], node_id)

        cluster = BenchmarkCluster(
            IPAddress('10.0.0.1'),
            lambda reactor: control_service,
            {},
            None,
        )
        operation = CreateContainer(clock, cluster)
        d = operation.get_probe()

        def run_probe(probe):
            def cleanup(result):
                cleaned_up = probe.cleanup()
                cleaned_up.addCallback(lambda _ignored: result)
                return cleaned_up
            d = probe.run()
            d.addCallback(cleanup)
            return d
        d.addCallback(run_probe)

        # Advance the clock because probe periodically polls the state.
        # Due to multiple steps, need to synchronize state a few times.
        control_service.synchronize_state()  # creation of pull container
        clock.advance(1)
        control_service.synchronize_state()  # deletion of pull container
        clock.advance(1)

        # The Deferred does not fire before the container has been created.
        self.assertNoResult(d)

        control_service.synchronize_state()  # creation of test container
        clock.advance(1)

        # The Deferred fires once the container has been created.
        self.successResultOf(d)

    def test_get_probe_timeout(self):
        """
        CreateContainer probe times-out if get_probe runs too long.
        """
        clock = Clock()

        node_id = uuid4()
        node = Node(uuid=node_id, public_address=IPAddress('10.0.0.1'))
        control_service = FakeFlockerClient([node], node_id)

        cluster = BenchmarkCluster(
            IPAddress('10.0.0.1'),
            lambda reactor: control_service,
            {},
            None,
        )
        operation = CreateContainer(clock, cluster)
        d = operation.get_probe()

        clock.advance(DEFAULT_TIMEOUT.total_seconds())

        # No control_service.synchronize_state() call, so cluster state
        # never shows container is created.

        # The Deferred fails if container not created within 10 minutes.
        self.failureResultOf(d)

    def test_run_probe_timeout(self):
        """
        CreateContainer probe times-out if probe.run runs too long.
        """
        clock = Clock()

        node_id = uuid4()
        node = Node(uuid=node_id, public_address=IPAddress('10.0.0.1'))
        control_service = FakeFlockerClient([node], node_id)

        cluster = BenchmarkCluster(
            IPAddress('10.0.0.1'),
            lambda reactor: control_service,
            {},
            None,
        )
        operation = CreateContainer(clock, cluster)
        d = operation.get_probe()

        control_service.synchronize_state()  # creation of pull container
        clock.advance(1)
        control_service.synchronize_state()  # deletion of pull container
        clock.advance(1)

        # get_probe has completed successfully
        probe = self.successResultOf(d)

        d = probe.run()

        clock.advance(DEFAULT_TIMEOUT.total_seconds())

        # No control_service.synchronize_state() call, so cluster state
        # never shows container is created.

        # The Deferred fails if container not created within 10 minutes.
        self.failureResultOf(d)

    def test_empty_cluster(self):
        """
        CreateContainer fails if no nodes in cluster.
        """
        control_service = FakeFlockerClient()

        cluster = BenchmarkCluster(
            IPAddress('10.0.0.1'),
            lambda reactor: control_service,
            {},
            None,
        )

        d = CreateContainer(Clock(), cluster).get_probe()

        self.failureResultOf(d, EmptyClusterError)
