# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for ``flocker.node.agents.blockdevice_manager``.
"""

from uuid import uuid4

from zope.interface.verify import verifyObject
from ....testtools import AsyncTestCase

from ..blockdevice_manager import (
    IBlockDeviceManager,
    BlockDeviceManager,
    MountInfo,
    MakeFilesystemError,
    MountError,
    UnmountError,
)

from .test_blockdevice import (
    loopbackblockdeviceapi_for_test,
    LOOPBACK_MINIMUM_ALLOCATABLE_SIZE,
    mountroot_for_test,
)


class BlockDeviceManagerTests(AsyncTestCase):
    """
    Tests for flocker.node.agents.blockdevice_manager.BlockDeviceManager.
    """

    def setUp(self):
        """
        Establish testing infrastructure for test cases.
        """
        super(BlockDeviceManager, self)
        self.loopback_api = loopbackblockdeviceapi_for_test(self)
        self.manager_under_test = BlockDeviceManager()
        self.mountroot = mountroot_for_test(self)

    def _get_directory_for_mount(self):
        """
        Construct a temporary directory to be used as a mountpoint.
        """
        directory = self.mountroot.child(str(uuid4()))
        directory.makedirs()
        return directory

    def _get_free_blockdevice(self):
        """
        Construct a new blockdevice for testing purposes.
        """
        volume = self.loopback_api.create_volume(
            dataset_id=uuid4(), size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE)
        self.loopback_api.attach_volume(
            volume.blockdevice_id, self.loopback_api.compute_instance_id())
        return self.loopback_api.get_device_path(volume.blockdevice_id)

    def test_implements_interface(self):
        """
        ``BlockDeviceManager`` implements ``IBlockDeviceManager``.
        """
        self.assertTrue(verifyObject(IBlockDeviceManager,
                                     self.manager_under_test))

    def test_get_mounts_shows_only_mounted(self):
        """
        Only mounted blockdevices appear in get_mounts.
        """
        blockdevice = self._get_free_blockdevice()
        mountpoint = self._get_directory_for_mount()
        self.manager_under_test.make_filesystem(blockdevice, 'ext4')
        self.manager_under_test.mount(blockdevice, mountpoint)
        mount_info = MountInfo(blockdevice=blockdevice, mountpoint=mountpoint)
        self.assertIn(mount_info, self.manager_under_test.get_mounts())
        self.manager_under_test.unmount(blockdevice)
        self.assertNotIn(mount_info, self.manager_under_test.get_mounts())

    def test_mount_multiple_times(self):
        """
        Mounting a device to n different locations requires n unmounts.

        Also verify they are unmounted in LIFO order.
        """
        blockdevice = self._get_free_blockdevice()
        self.manager_under_test.make_filesystem(blockdevice, 'ext4')
        mountpoints = list(self._get_directory_for_mount() for _ in xrange(4))
        for mountpoint in mountpoints:
            self.manager_under_test.mount(blockdevice, mountpoint)

        mount_infos = list(MountInfo(blockdevice=blockdevice,
                                     mountpoint=mountpoint)
                           for mountpoint in mountpoints)
        while mount_infos:
            self.assertSetEqual(
                set(mount_infos),
                set(m for m in self.manager_under_test.get_mounts()
                    if m.blockdevice == blockdevice))
            self.manager_under_test.unmount(blockdevice)
            mount_infos.pop()
        self.assertFalse(any(m.blockdevice == blockdevice
                             for m in self.manager_under_test.get_mounts()))

    def test_mount_multiple_blockdevices(self):
        """
        Mounting multiple devices to the same mountpoint.

        Note that the blockdevices must be unmounted in reverse order,
        otherwise the unmount operations will fail.
        """
        blockdevices = list(self._get_free_blockdevice() for _ in xrange(4))
        mountpoint = self._get_directory_for_mount()
        for blockdevice in blockdevices:
            self.manager_under_test.make_filesystem(blockdevice, 'ext4')
            self.manager_under_test.mount(blockdevice, mountpoint)

        mount_infos = list(MountInfo(blockdevice=blockdevice,
                                     mountpoint=mountpoint)
                           for blockdevice in blockdevices)

        blockdevices.reverse()
        for blockdevice in blockdevices:
            self.assertSetEqual(
                set(mount_infos),
                set(m for m in self.manager_under_test.get_mounts()
                    if m.mountpoint == mountpoint))
            self.manager_under_test.unmount(blockdevice)
            mount_infos = list(m for m in mount_infos
                               if m.blockdevice != blockdevice)

        self.assertSetEqual(
            set(), set(m for m in self.manager_under_test.get_mounts()
                       if m.mountpoint == mountpoint))

    def test_unmount_unmounted(self):
        """
        Errors in unmounting raise an ``UnmountError``.
        """
        blockdevice = self._get_free_blockdevice()
        with self.assertRaisesRegexp(UnmountError, blockdevice.path):
            self.manager_under_test.unmount(blockdevice)

    def test_mount_unformatted(self):
        """
        Errors in mounting raise a ``MountError``.
        """
        blockdevice = self._get_free_blockdevice()
        mountpoint = self._get_directory_for_mount()
        with self.assertRaisesRegexp(MountError, blockdevice.path):
            self.manager_under_test.mount(blockdevice, mountpoint)

    def test_formatted_bad_type(self):
        """
        Errors in formatting raise a ``MakeFilesystemError``.
        """
        blockdevice = self._get_free_blockdevice()
        with self.assertRaisesRegexp(MakeFilesystemError, blockdevice.path):
            self.manager_under_test.make_filesystem(blockdevice, 'myfakeyfs')
