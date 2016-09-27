# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for ``flocker.node.agents.loopback``.
"""
from ..loopback import Losetup, LOOPBACK_MINIMUM_ALLOCATABLE_SIZE

from ....testtools import TestCase, if_root


class LosetupTests(TestCase):
    """
    Tests for ``Losetup``.
    """
    @if_root
    def setUp(self):
        return super(LosetupTests, self).setUp()

    def test_success(self):
        """
        ``Losetup.add`` creates a device that is listed.
        """
        loop = Losetup()
        backing_file = self.make_temporary_file()
        with backing_file.open('wb') as f:
            f.truncate(LOOPBACK_MINIMUM_ALLOCATABLE_SIZE)

        device = loop.add(backing_file)
        self.addCleanup(device.remove)
        self.assertIn(device, loop.list())
