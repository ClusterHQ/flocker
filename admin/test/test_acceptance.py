# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
"""
Tests for ``admin.acceptance``.
"""

from zope.interface.verify import verifyObject
from twisted.trial.unittest import SynchronousTestCase

from ..acceptance import IClusterRunner, ManagedRunner

from flocker.provision import PackageSource
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
