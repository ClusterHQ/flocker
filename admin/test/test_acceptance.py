# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
"""
Tests for ``admin.acceptance``.
"""

from zope.interface.verify import verifyObject
from twisted.trial.unittest import SynchronousTestCase

from ..acceptance import IClusterRunner, ManagedRunner


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
            distribution=b'centos-7'
        )
        self.assertTrue(
            verifyObject(IClusterRunner, runner)
        )
