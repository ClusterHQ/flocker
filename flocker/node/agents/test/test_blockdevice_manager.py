# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for ``flocker.node.agents.blockdevice_manager``.
"""

from uuid import uuid4

from testtools import ExpectedException
from testtools.matchers import (
    AnyMatch,
    AllMatch,
    Contains,
    FileExists,
    HasLength,
    MatchesAll,
    MatchesSetwise,
    MatchesStructure,
    Not,
)
from twisted.python.filepath import FilePath
from zope.interface.verify import verifyObject

from ....testtools import TestCase

from ..blockdevice_manager import (
    BindMountError,
    BlockDeviceManager,
    DetailedMountInfo,
    IBlockDeviceManager,
    MakeFilesystemError,
    MakeTmpfsMountError,
    MountError,
    MountType,
    Permissions,
    RemountError,
    ShareMountError,
    SystemFileLocation,
    UnmountError,
)

from .test_blockdevice import (
    loopbackblockdeviceapi_for_test,
    LOOPBACK_MINIMUM_ALLOCATABLE_SIZE,
    mountroot_for_test,
)

from ..testtools import CleanupBlockDeviceManager


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

    def test_get_all_mounts_shows_all_types(self):
        """
        bind mounts, tmpfs mounts, and disk mounts show up in get_all_mounts.
        """
        blockdevice = self._get_free_blockdevice()
        blockdevice_mountpoint = self._get_directory_for_mount()
        tmpfs_mountpoint = self._get_directory_for_mount()
        bind_mountpoint = self._get_directory_for_mount()
        self.manager_under_test.make_filesystem(blockdevice, 'ext4')
        self.manager_under_test.mount(blockdevice, blockdevice_mountpoint)
        self.manager_under_test.make_tmpfs_mount(tmpfs_mountpoint)
        self.manager_under_test.bind_mount(tmpfs_mountpoint, bind_mountpoint)
        self.manager_under_test.remount(bind_mountpoint, Permissions.READ_ONLY)
        mounts = self.manager_under_test.get_all_mounts()
        blockdevice_st_dev = next(x.root_location.st_dev
                                  for x in mounts
                                  if (x.mount_type == MountType.BLOCKDEVICE and
                                      x.blockdevice == blockdevice))
        tmpfs_st_dev = next(x.root_location.st_dev
                            for x in mounts
                            if x.mountpoint == tmpfs_mountpoint)
        mount_infos = {
            DetailedMountInfo(
                mount_type=MountType.BLOCKDEVICE,
                permissions=Permissions.READ_WRITE,
                blockdevice=blockdevice,
                mountpoint=blockdevice_mountpoint,
                root_location=SystemFileLocation(
                    st_dev=blockdevice_st_dev,
                    path=FilePath("/"),
                )
            ),
            DetailedMountInfo(
                mount_type=MountType.TMPFS,
                permissions=Permissions.READ_WRITE,
                mountpoint=tmpfs_mountpoint,
                root_location=SystemFileLocation(
                    st_dev=tmpfs_st_dev,
                    path=FilePath("/"),
                )
            ),
            DetailedMountInfo(
                mount_type=MountType.TMPFS,
                permissions=Permissions.READ_ONLY,
                mountpoint=bind_mountpoint,
                root_location=SystemFileLocation(
                    st_dev=tmpfs_st_dev,
                    path=FilePath("/"),
                )
            ),
        }
        self.expectThat(self.manager_under_test.get_all_mounts(),
                        MatchesAll(*map(Contains, mount_infos)))
        self.manager_under_test.unmount(bind_mountpoint)
        self.manager_under_test.unmount(tmpfs_mountpoint)
        self.manager_under_test.unmount(blockdevice_mountpoint)

    def test_get_disk_mounts_shows_only_mounted(self):
        """
        Only mounted blockdevices appear in get_disk_mounts.
        """
        blockdevice = self._get_free_blockdevice()
        mountpoint = self._get_directory_for_mount()
        self.manager_under_test.make_filesystem(blockdevice, 'ext4')
        self.manager_under_test.mount(blockdevice, mountpoint)
        matches_blockdevice = MatchesStructure.byEquality(
            mount_type=MountType.BLOCKDEVICE,
            permissions=Permissions.READ_WRITE,
            blockdevice=blockdevice,
            mountpoint=mountpoint
        )
        self.assertThat(
            self.manager_under_test.get_disk_mounts(),
            AnyMatch(matches_blockdevice)
        )
        self.manager_under_test.unmount(blockdevice)
        self.assertThat(
            self.manager_under_test.get_disk_mounts(),
            AllMatch(Not(matches_blockdevice))
        )

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

        matches_mounts = list(
            MatchesStructure.byEquality(
                mount_type=MountType.BLOCKDEVICE,
                permissions=Permissions.READ_WRITE,
                blockdevice=blockdevice,
                mountpoint=mountpoint
            ) for mountpoint in mountpoints)
        while matches_mounts:
            self.assertThat(
                set(m for m in self.manager_under_test.get_disk_mounts()
                    if m.blockdevice == blockdevice),
                MatchesSetwise(*matches_mounts)
            )
            self.manager_under_test.unmount(blockdevice)
            matches_mounts.pop()
        self.assertFalse(
            any(m.blockdevice == blockdevice
                for m in self.manager_under_test.get_disk_mounts())
        )

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

        matches_dicts = list(
            dict(
                mount_type=MountType.BLOCKDEVICE,
                permissions=Permissions.READ_WRITE,
                blockdevice=blockdevice,
                mountpoint=mountpoint
            ) for blockdevice in blockdevices)

        blockdevices.reverse()
        for blockdevice in blockdevices:
            self.assertThat(
                set(m for m in self.manager_under_test.get_disk_mounts()
                    if m.mountpoint == mountpoint),
                MatchesSetwise(*list(
                    MatchesStructure.byEquality(**kw)
                    for kw in matches_dicts
                )),
            )
            self.manager_under_test.unmount(blockdevice)
            matches_dicts = list(m for m in matches_dicts
                                 if m['blockdevice'] != blockdevice)

        self.assertSetEqual(
            set(), set(m for m in self.manager_under_test.get_disk_mounts()
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
        self.addCleanup(self.manager_under_test.unmount, target_directory)
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

    def test_shared_mount(self):
        """
        If a mount is shared then submounts are reflected in directories that
        are bind mounted.
        """
        bounddir = self._get_directory_for_mount()
        mountdir = self._get_directory_for_mount()
        submountdir = mountdir.child('sub')
        submountclone = bounddir.child('sub')
        self.manager_under_test.make_tmpfs_mount(mountdir)
        self.addCleanup(lambda: self.manager_under_test.unmount(mountdir))
        self.manager_under_test.share_mount(mountdir)
        self.manager_under_test.bind_mount(mountdir, bounddir)
        self.addCleanup(lambda: self.manager_under_test.unmount(bounddir))
        submountdir.makedirs()
        self.manager_under_test.make_tmpfs_mount(submountdir)
        self.addCleanup(lambda: self.manager_under_test.unmount(submountdir))
        submountdir.child('subsub').touch()
        self.assertThat(submountclone.child('subsub').path, FileExists())

    def test_shared_mount_failure(self):
        """
        Attempting to share a directory that is not a mount raises a
        :class:`ShareMountError` that has the name of the attempted mount
        point.
        """
        fakemountdir = self._get_directory_for_mount().child('fakeyfake')
        with ExpectedException(ShareMountError, '.*fakeyfake.*'):
            self.manager_under_test.share_mount(fakemountdir)


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
        self.assertThat(self.manager_under_test._cleanup_operations,
                        HasLength(1))
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
            [mountdir_1, mountdir_2, mountdir_4])

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
        basedir = self._get_directory_for_mount()
        self.manager_under_test.bind_mount(basedir, bounddir)
        self.assertEqual(len(self.manager_under_test._cleanup_operations), 1)
        self.assertEqual(
            self.manager_under_test._cleanup_operations[0].path,
            bounddir)
        self.manager_under_test.unmount(bounddir)
