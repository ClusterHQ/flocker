# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for ``flocker.node.agents.blockdevice_manager``.
"""

from uuid import uuid4

from pyrsistent import PClass, field
from testtools import ExpectedException
from testtools.matchers import Not, FileExists
from twisted.python.components import proxyForInterface
from twisted.python.filepath import FilePath
from zope.interface import Interface, implementer
from zope.interface.verify import verifyObject

from ....testtools import TestCase

from ..blockdevice_manager import (
    BindMountError,
    BlockDeviceManager,
    IBlockDeviceManager,
    MakeFilesystemError,
    MakeTmpfsMountError,
    MountError,
    MountInfo,
    Permissions,
    RemountError,
    UnmountError,
)

from .test_blockdevice import (
    loopbackblockdeviceapi_for_test,
    LOOPBACK_MINIMUM_ALLOCATABLE_SIZE,
    mountroot_for_test,
)


def blockdevice_manager_for_test(test_case):
    """
    Creates a blockdevice_manager that cleans itself up during test cleanup.

    Cleanup is defined as unmounting all bind mounts, tmpfs mounts, and
    blockdevice mounts.

    :param test_case: The :class:`TestCase` to use to add cleanup callbacks.
    """
    manager = CleanupBlockDeviceManager(BlockDeviceManager())
    test_case.addCleanup(manager.cleanup)
    return manager


class BlockDeviceManagerTests(TestCase):
    """
    Tests for flocker.node.agents.blockdevice_manager.BlockDeviceManager.
    """

    def setUp(self):
        """
        Establish testing infrastructure for test cases.
        """
        super(BlockDeviceManagerTests, self).setUp()
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

    def test_bind_mount(self):
        """
        Files created in a bind mount are visible in the original folder and
        vice versa.
        """
        src_directory = self._get_directory_for_mount()
        target_directory = self._get_directory_for_mount()
        self.manager_under_test.bind_mount(src_directory, target_directory)
        for create, view in [(target_directory, src_directory),
                             (src_directory, target_directory)]:
            filename = str(uuid4())
            new_file = create.child(filename)
            new_file.touch()
            self.expectThat(view.child(filename).path, FileExists(),
                            'Created file not visible through bind mount.')

    def test_failing_bind_mount(self):
        """
        Attempts to bind mount to a mountpoint that does not exist fail with a
        ``BindMountError``.
        """
        src_directory = self._get_directory_for_mount()
        target_directory = self._get_directory_for_mount().child('nonexistent')
        with ExpectedException(BindMountError, '.*nonexistent.*'):
            self.manager_under_test.bind_mount(src_directory, target_directory)

    def test_remount(self):
        """
        Mounts remounted read-only cannot be written to until they are
        remounted read-write.
        """
        blockdevice = self._get_free_blockdevice()
        mountpoint = self._get_directory_for_mount()
        self.manager_under_test.make_filesystem(blockdevice, 'ext4')
        self.manager_under_test.mount(blockdevice, mountpoint)

        first_file = mountpoint.child(str(uuid4()))
        second_file = mountpoint.child(str(uuid4()))
        third_file = mountpoint.child(str(uuid4()))

        first_file.touch()
        self.expectThat(first_file.path, FileExists())

        self.manager_under_test.remount(mountpoint, Permissions.READ_ONLY)
        self.expectThat(first_file.path, FileExists())

        with ExpectedException(OSError):
            second_file.touch()
        self.expectThat(second_file.path, Not(FileExists()))

        self.manager_under_test.remount(mountpoint, Permissions.READ_WRITE)
        self.expectThat(first_file.path, FileExists())
        self.expectThat(second_file.path, Not(FileExists()))
        third_file.touch()
        self.expectThat(third_file.path, FileExists())

    def test_remount_failure(self):
        """
        Remounts of a folder that is not mounted fail with ``RemountError``.
        """
        unmounted_directory = self._get_directory_for_mount()
        with ExpectedException(RemountError):
            self.manager_under_test.remount(unmounted_directory,
                                            Permissions.READ_WRITE)

    def test_make_tmpfs_mount(self):
        """
        make_tmpfs_mount creates a tmpfs mountpoint that can be written to.
        Once the mount is unmounted all files are gone.
        """
        mountpoint = self._get_directory_for_mount()

        test_file = mountpoint.child(unicode(uuid4()))

        self.manager_under_test.make_tmpfs_mount(mountpoint)
        self.expectThat(test_file.path, Not(FileExists()))
        test_file.touch()
        self.expectThat(test_file.path, FileExists(),
                        'File did not exist after being touched on tmpfs.')
        self.manager_under_test.unmount(mountpoint)
        self.expectThat(test_file.path, Not(FileExists()),
                        'File persisted after tmpfs mount unmounted')

    def test_make_tmpfs_mount_failure(self):
        """
        make_tmpfs_mount errors with a ``MakeTmpfsMountError`` if the mount
        point does not exist.
        """
        non_existent = self._get_directory_for_mount().child('non_existent')
        with ExpectedException(MakeTmpfsMountError, '.*non_existent.*'):
            self.manager_under_test.make_tmpfs_mount(non_existent)


class _ICleanupOperation(Interface):
    """
    Interface for cleanup operations.
    """

    def execute(blockdevice_manager):
        """
        Perform the cleanup operation.

        :param blockdevice_manager: The :class:`IBlockDeviceManager` provider
            to use to execute the cleanup.
        """


@implementer(_ICleanupOperation)
class _UnmountCleanup(PClass):
    """
    Object for cleanup by unmounting.

    :ivar FilePath path: The path to unmount.
    """
    path = field(type=FilePath)

    def execute(self, blockdevice_manager):
        blockdevice_manager.unmount(self.path)


class CleanupBlockDeviceManager(proxyForInterface(IBlockDeviceManager)):
    """
    Proxies to another :class:`IBlockDeviceManager` provider, and records every
    created mount, symlink, etc. for cleanup later.

    This is a test helper class for tests that use
    :class:`IBlockDeviceManager`, and don't want to manually manage cleanup of
    all of the mounts and symlinks.

    Note: This does not behave precisely correct for mounted blockdevices that
    are unmounted by mount point.

    :ivar _cleanup_operations: A list of operations to perform upon cleanup in
        reverse order. These must provide :class:`_ICleanupOperation`.
    """
    def __init__(self, original):
        super(CleanupBlockDeviceManager, self).__init__(original)
        self._cleanup_operations = []

    def mount(self, blockdevice, mountpoint):
        self._cleanup_operations.append(_UnmountCleanup(path=blockdevice))
        self.original.mount(blockdevice, mountpoint)

    def unmount(self, unmount_path):
        unmount_index = next(iter(
            -index
            for index, op in enumerate(reversed(self._cleanup_operations), 1)
            if op == _UnmountCleanup(path=unmount_path)
        ), None)
        if unmount_path is not None:
            self._cleanup_operations.pop(unmount_index)
        self.original.unmount(unmount_path)

    def make_tmpfs_mount(self, mountpoint):
        self._cleanup_operations.append(_UnmountCleanup(path=mountpoint))
        self.original.make_tmpfs_mount(mountpoint)

    def bind_mount(self, source_path, mountpoint):
        self._cleanup_operations.append(_UnmountCleanup(path=mountpoint))
        self.original.bind_mount(source_path, mountpoint)

    def cleanup(self):
        """
        Perform all cleanup operations.
        """
        for operation in reversed(self._cleanup_operations):
            operation.execute(self.original)


class CleanupBlockDeviceManagerTests(TestCase):
    """
    Test for :class:`CleanupBlockDeviceManager`.
    """

    def setUp(self):
        super(CleanupBlockDeviceManagerTests, self).setUp()
        self.loopback_api = loopbackblockdeviceapi_for_test(self)
        self.manager_under_test = CleanupBlockDeviceManager(
            BlockDeviceManager())
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

    def test_mount_cleaned_up(self):
        """
        The cleanup implementation cleans up mounts.
        """
        blockdevice = self._get_free_blockdevice()
        self.manager_under_test.make_filesystem(blockdevice, 'ext4')
        mountdir = self._get_directory_for_mount()
        self.manager_under_test.mount(blockdevice, mountdir)
        self.assertEqual(len(self.manager_under_test._cleanup_operations), 1)
        self.assertIn(
            self.manager_under_test._cleanup_operations[0].path,
            [blockdevice, mountdir])

    def test_unmounted_not_cleaned_up(self):
        """
        The cleanup implementation not cleanup mounts that are unmounted.
        """
        blockdevice = self._get_free_blockdevice()
        self.manager_under_test.make_filesystem(blockdevice, 'ext4')
        mountdir = self._get_directory_for_mount()
        self.manager_under_test.mount(blockdevice, mountdir)
        self.manager_under_test.unmount(blockdevice)
        self.assertEqual(len(self.manager_under_test._cleanup_operations), 0)

    def test_clean_up_from_end(self):
        """
        The cleanup implementation not cleanup mounts that are unmounted. These
        are removed in reverse order.
        """
        blockdevice_1 = self._get_free_blockdevice()
        blockdevice_2 = self._get_free_blockdevice()
        self.manager_under_test.make_filesystem(blockdevice_1, 'ext4')
        self.manager_under_test.make_filesystem(blockdevice_2, 'ext4')
        mountdir_1 = self._get_directory_for_mount()
        mountdir_2 = self._get_directory_for_mount()
        mountdir_3 = self._get_directory_for_mount()
        mountdir_4 = self._get_directory_for_mount()
        self.manager_under_test.mount(blockdevice_1, mountdir_1)
        self.manager_under_test.mount(blockdevice_2, mountdir_2)
        self.manager_under_test.mount(blockdevice_1, mountdir_3)
        self.manager_under_test.mount(blockdevice_2, mountdir_4)
        self.manager_under_test.unmount(blockdevice_1)
        self.assertEqual(
            list(x.path for x in self.manager_under_test._cleanup_operations),
            [blockdevice_1, blockdevice_2, blockdevice_2])

    def test_tmpfs_mount_cleaned_up(self):
        """
        The cleanup implementation cleans up tmpfs mounts.
        """
        mountdir = self._get_directory_for_mount()
        self.manager_under_test.make_tmpfs_mount(mountdir)
        self.assertEqual(len(self.manager_under_test._cleanup_operations), 1)
        self.assertEqual(
            self.manager_under_test._cleanup_operations[0].path,
            mountdir)
        self.manager_under_test.unmount(mountdir)

    def test_bind_mount_cleaned_up(self):
        """
        The cleanup implementation cleans up bind mounts.
        """
        bounddir = self._get_directory_for_mount()
        mountdir = self._get_directory_for_mount()
        self.manager_under_test.bind_mount(bounddir, mountdir)
        self.assertEqual(len(self.manager_under_test._cleanup_operations), 1)
        self.assertEqual(
            self.manager_under_test._cleanup_operations[0].path,
            mountdir)
        self.manager_under_test.unmount(mountdir)
