# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for ``flocker.node.agents.blockdevice_manager``.
"""

from uuid import uuid4

from twisted.trial.unittest import SynchronousTestCase

from ..blockdevice_manager import BlockDeviceManager, MountInfo
from .test_blockdevice import (
    loopbackblockdeviceapi_for_test,
    LOOPBACK_MINIMUM_ALLOCATABLE_SIZE,
    mountroot_for_test,
)


class BlockDeviceManagerTests(SynchronousTestCase):
    """Tests for flocker.node.agents.blockdevice_manager.BlockDeviceManager

    XXX: Turn this into a test generator once we have a verified fake.
    """

    def setUp(self):
        """Creates a loopback BlockDeviceAPI for creating blockdevices."""
        self.loopback_api = loopbackblockdeviceapi_for_test(self)
        self.manager_under_test = BlockDeviceManager()
        self.mountroot = mountroot_for_test(self)

    def _get_directory_for_mount(self):
        directory = self.mountroot.child(str(uuid4()))
        # This is unneeded for testing fakes.
        directory.makedirs()
        return directory

    def _get_free_blockdevice(self):
        # This is unneeded for testing fakes.
        volume = self.loopback_api.create_volume(
            dataset_id=uuid4(), size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE)
        self.loopback_api.attach_volume(
            volume.blockdevice_id, self.loopback_api.compute_instance_id())
        return self.loopback_api.get_device_path(volume.blockdevice_id)

    def test_happy_case(self):
        """Mounted blockdevices should appear in get_mounts."""
        blockdevice = self._get_free_blockdevice()
        mountpoint = self._get_directory_for_mount()
        self.manager_under_test.make_filesystem(blockdevice, 'ext4')
        self.manager_under_test.mount(blockdevice, mountpoint)
        mount_info = MountInfo(blockdevice=blockdevice, mountpoint=mountpoint)
        self.assertIn(mount_info, self.manager_under_test.get_mounts())
        self.manager_under_test.unmount(blockdevice)
        self.assertNotIn(mount_info, self.manager_under_test.get_mounts())

