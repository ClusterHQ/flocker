# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
"""
Tests for ``admin.acceptance``.
"""

from uuid import UUID

from zope.interface.verify import verifyObject
from twisted.trial.unittest import SynchronousTestCase

from ..acceptance import (
    IClusterRunner, ManagedRunner, generate_certificates,
    DISTRIBUTIONS,
)

from flocker.ca import RootCredential
from flocker.provision import PackageSource
from flocker.provision._install import ManagedNode
from flocker.acceptance.testtools import DatasetBackend


class ManagedRunnerTests(SynchronousTestCase):
    """
    Tests for ``ManagedRunner``.
    """
    def test_interface(self):
        """
        ``ManagedRunner`` provides ``IClusterRunner``.
        """
        runner = ManagedRunner(
            node_addresses=[b'192.0.2.1'],
            package_source=PackageSource(
                version=b"",
                os_version=b"",
                branch=b"",
                build_server=b"",
            ),
            distribution=b'centos-7',
            dataset_backend=DatasetBackend.zfs,
            dataset_backend_configuration={},
        )
        self.assertTrue(
            verifyObject(IClusterRunner, runner)
        )


class GenerateCertificatesTests(SynchronousTestCase):
    """
    Tests for ``generate_certificates``.
    """
    def test_cluster_id(self):
        """
        The certificates generated are for a cluster with the given identifier.
        """
        cluster_id = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
        node = ManagedNode(
            address=b"192.0.2.17", distribution=DISTRIBUTIONS[0],
        )
        certificates = generate_certificates(cluster_id, [node])
        root = RootCredential.from_path(certificates.directory)
        self.assertEqual(
            cluster_id,
            UUID(root.organizational_unit),
        )
