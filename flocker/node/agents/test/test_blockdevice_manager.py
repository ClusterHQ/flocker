# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for ``flocker.node.agents.blockdevice_manager``.
"""
from subprocess import CalledProcessError
from uuid import uuid4

from testtools import ExpectedException
from testtools.matchers import Not, FileExists

from zope.interface.verify import verifyObject

from ....testtools import TestCase, random_name, if_root

from ..loopback import LOOPBACK_MINIMUM_ALLOCATABLE_SIZE
from ..blockdevice_manager import (
    BindMountError,
    BlockDeviceManager,
    IBlockDeviceManager,
    LabelMounter,
    MakeFilesystemError,
    MakeTmpfsMountError,
    MountError,
    MountInfo,
    Permissions,
    RemountError,
    temporary_mount,
    mount,
    UnmountError,
)
from ..testtools import (
    filesystem_label_for_test,
    formatted_loopback_device_for_test,
    loopbackblockdeviceapi_for_test,
    mountroot_for_test,
)


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
        make_tmpfs_mount should create a tmpfs mountpoint that can be written
        to. Once the mount is unmounted all files should be gone.
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


class MountTests(TestCase):
    """
    Tests for ``mount``.
    """
    @if_root
    def setUp(self):
        super(MountTests, self).setUp()
        self.device = formatted_loopback_device_for_test(self)

    def test_success(self):
        """
        ``mount`` mounts the supplied device and returns a
        ``MountedFileSystem`` that can be unmounted.
        ``MountedFileSystem.unmount`` can be idempotent.
        The files added to mountpoint are stored on the filesystem rather than
        in the mountpoint directory.
        """
        filename = random_name(self)
        filecontent = random_name(self)
        mountpoint1 = self.make_temporary_directory()
        fs1 = mount(self.device.device, mountpoint1)
        # This succeeds even though the fs has already been unmounted below.
        self.addCleanup(fs1.unmount, idempotent=True)
        fs1.mountpoint.child(filename).setContent(filecontent)
        fs1.unmount()
        # ``unmount`` will fail unless the mountpoint is mounted or you specify
        # idempotent=True
        self.assertRaises(CalledProcessError, fs1.unmount)

        self.assertEqual([], mountpoint1.children())
        mountpoint2 = self.make_temporary_directory()
        fs2 = mount(self.device.device, mountpoint2)
        self.addCleanup(fs2.unmount, idempotent=True)
        self.assertEqual(
            filecontent,
            fs2.mountpoint.child(filename).getContent()
        )

    def test_context_manager(self):
        """
        When used as a context manager, the filesystem is unmounted on exiting
        the context.
        """
        filename = random_name(self)
        filecontent = random_name(self)
        mountpoint = self.make_temporary_directory()
        with mount(self.device.device, mountpoint) as fs:
            self.addCleanup(fs.unmount, idempotent=True)
            mountpoint.child(filename).setContent(filecontent)
        self.assertEqual([], mountpoint.children())
        with mount(self.device.device, mountpoint) as fs:
            self.addCleanup(fs.unmount, idempotent=True)
            self.assertEqual(
                filecontent,
                mountpoint.child(filename).getContent()
            )

    def test_context_manager_error(self):
        """
        When used as a context manager, the filesystem is unmounted even if
        exceptions are raised.
        """
        class SomeException(Exception):
            pass
        filename = random_name(self)
        filecontent = random_name(self)
        mountpoint = self.make_temporary_directory()
        try:
            with mount(self.device.device, mountpoint) as fs:
                self.addCleanup(fs.unmount, idempotent=True)
                with fs.mountpoint.child(filename).open('w') as f:
                    f.write(filecontent)
                raise SomeException()
        except SomeException:
            self.assertEqual([], mountpoint.children())
        else:
            self.fail("The expected ``SomeException`` was not raised.")


class TemporaryMountTests(TestCase):
    """
    Tests for ``temporary_mount``.
    """
    @if_root
    def setUp(self):
        super(TemporaryMountTests, self).setUp()
        self.device = formatted_loopback_device_for_test(self)

    def test_success(self):
        """
        ``temporary_mount`` mounts the supplied device at a temporary
        directory.
        The temporary directory is removed when it is unmounted.
        """
        filename = random_name(self)
        filecontent = random_name(self)
        fs1 = temporary_mount(self.device.device)
        self.addCleanup(fs1.unmount, idempotent=True)
        fs1.mountpoint.child(filename).setContent(filecontent)
        fs2 = temporary_mount(self.device.device)
        self.addCleanup(fs2.unmount, idempotent=True)
        self.assertEqual(
            filecontent,
            fs2.mountpoint.child(filename).getContent()
        )
        fs1.unmount()
        fs2.unmount()
        self.assertEqual(
            (False, False),
            (fs1.mountpoint.exists(), fs2.mountpoint.exists())
        )

    def test_context_manager(self):
        """
        ``temporary_mount`` when used as a context manager will unmount and
        remove the temporary mountpoint on context exit.
        """
        filename = random_name(self)
        filecontent = random_name(self)
        mounts = []
        with temporary_mount(self.device.device) as fs:
            mounts.append(fs)
            fs.mountpoint.child(filename).setContent(filecontent)
        self.assertFalse(mounts[0].mountpoint.exists())

        with temporary_mount(self.device.device) as fs:
            mounts.append(fs)
            self.assertEqual(
                filecontent,
                fs.mountpoint.child(filename).getContent()
            )
        self.assertFalse(mounts[1].mountpoint.exists())
        self.assertNotEqual(*mounts)


class LabelMounterTests(TestCase):
    """
    Tests for ``LabelMounter``.
    """
    @if_root
    def setUp(self):
        super(LabelMounterTests, self).setUp()
        self.label = filesystem_label_for_test(self)
        self.device = formatted_loopback_device_for_test(
            self, label=self.label
        )

    def test_success(self):
        """
        ``LabelMounter`` can mount a filesystem based on its LABEL.
        """
        filename = random_name(self)
        filecontent = random_name(self)
        mountpoint1 = self.make_temporary_directory()
        with LabelMounter(label=self.label).mount(mountpoint1):
            mountpoint1.child(filename).setContent(filecontent)
        mountpoint2 = self.make_temporary_directory()
        with LabelMounter(label=self.label).mount(mountpoint2):
            self.assertEqual(
                filecontent,
                mountpoint2.child(filename).getContent()
            )

    def test_label_not_found(self):
        """
        ``MountError`` is raised if the supplied filesystem label is not found.
        """
        non_existent_label = filesystem_label_for_test(self)
        mountpoint1 = self.make_temporary_path()
        mounter = LabelMounter(label=non_existent_label)
        e = self.assertRaises(
            MountError,
            mounter.mount,
            mountpoint1,
        )
        self.assertIn(non_existent_label, unicode(e))
