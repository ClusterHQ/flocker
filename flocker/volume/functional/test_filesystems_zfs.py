# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""Functional tests for ZFS filesystem implementation.

Further coverage is provided in
:module:`flocker.volume.test.test_filesystems_zfs`.
"""

import subprocess
import errno

from twisted.internet import reactor
from twisted.trial.unittest import TestCase
from twisted.python.filepath import FilePath

from ..test.filesystemtests import (
    make_ifilesystemsnapshots_tests, make_istoragepool_tests, create_and_copy,
    )
from ..filesystems.zfs import (
    ZFSSnapshots, Filesystem, StoragePool, volume_to_dataset,
    )
from ..service import Volume
from ..testtools import create_zfs_pool, service_for_pool


class IFilesystemSnapshotsTests(make_ifilesystemsnapshots_tests(
        lambda test_case: ZFSSnapshots(
            reactor, Filesystem(create_zfs_pool(test_case), None)))):
    """``IFilesystemSnapshots`` tests for ZFS."""


class IStoragePoolTests(make_istoragepool_tests(
    lambda test_case: StoragePool(reactor, create_zfs_pool(test_case),
                                  FilePath(test_case.mktemp())))):
    """``IStoragePoolTests`` for ZFS storage pool."""


class VolumeToDatasetTests(TestCase):
    """Tests for ``volume_to_dataset``."""
    def test_volume_to_dataset(self):
        """``volume_to_dataset`` includes the UUID, dataset
        name and (for future functionality) a default branch name.
        """
        volume = Volume(uuid=u"my-uuid", name=u"myvolumename", service=None)
        self.assertEqual(volume_to_dataset(volume),
                         b"my-uuid.myvolumename")


class StoragePoolTests(TestCase):
    """ZFS-specific ``StoragePool`` tests."""

    def test_mount_root(self):
        """Mountpoints are children of the mount root."""
        mount_root = FilePath(self.mktemp())
        mount_root.makedirs()
        pool = StoragePool(reactor, create_zfs_pool(self), mount_root)
        service = service_for_pool(self, pool)
        volume = service.get(u"myvolumename")

        d = pool.create(volume)

        def gotFilesystem(filesystem):
            self.assertEqual(filesystem.get_path(),
                             mount_root.child(volume_to_dataset(volume)))
        d.addCallback(gotFilesystem)
        return d

    def test_filesystem_identity(self):
        """Filesystems are created with the correct pool and dataset names."""
        mount_root = FilePath(self.mktemp())
        pool_name = create_zfs_pool(self)
        pool = StoragePool(reactor, pool_name, mount_root)
        service = service_for_pool(self, pool)
        volume = service.get(u"myvolumename")

        d = pool.create(volume)

        def gotFilesystem(filesystem):
            self.assertEqual(
                filesystem,
                Filesystem(pool_name, volume_to_dataset(volume)))
        d.addCallback(gotFilesystem)
        return d

    def test_actual_mountpoint(self):
        """The mountpoint of the filesystem is the actual ZFS mountpoint."""
        mount_root = FilePath(self.mktemp())
        pool_name = create_zfs_pool(self)
        pool = StoragePool(reactor, pool_name, mount_root)
        service = service_for_pool(self, pool)
        volume = service.get(u"myvolumename")

        d = pool.create(volume)

        def gotFilesystem(filesystem):
            self.assertEqual(
                filesystem.get_path().path,
                subprocess.check_output(
                    [b"zfs", b"get", b"-H", b"-o", b"value",
                     b"mountpoint", filesystem.name]).strip())
        d.addCallback(gotFilesystem)
        return d

    def test_change_owner_does_not_remove_non_empty_mountpoint(self):
        """
        ``StoragePool.change_owner()`` doesn't delete the contents of the
        original mountpoint, if it is non-empty.

        ZFS doesn't like to mount volumes over non-empty directories. To test
        this, we change the original mount to be a legacy mount (mounted using
        manpage:`mount(8)`).
        """
        pool = StoragePool(reactor, create_zfs_pool(self),
                           FilePath(self.mktemp()))
        service = service_for_pool(self, pool)
        volume = service.get(u"myvolumename")
        new_volume = Volume(uuid=u"other-uuid", name=u"volume",
                            service=service)
        original_mount = volume.get_filesystem().get_path()
        d = pool.create(volume)

        def created_filesystems(ignored):
            filesystem_name = volume.get_filesystem().name
            subprocess.check_call(['zfs', 'unmount', filesystem_name])
            # Create a file hiding under the original mount point
            original_mount.child('file').setContent('content')
            # Remount the volume at the original mount point as a legacy mount.
            subprocess.check_call(['zfs', 'set', 'mountpoint=legacy',
                                   filesystem_name])
            subprocess.check_call(['mount', '-t', 'zfs', filesystem_name,
                                   original_mount.path])
            return pool.change_owner(volume, new_volume)
        d.addCallback(created_filesystems)

        self.assertFailure(d, OSError)

        def changed_owner(filesystem):
            self.assertEqual(original_mount.child('file').getContent(),
                             b'content')
        d.addCallback(changed_owner)
        return d

    def test_locally_owned_created_writeable(self):
        """
        A filesystem which is created for a locally owned volume is writeable.
        """
        pool = StoragePool(reactor, create_zfs_pool(self),
                           FilePath(self.mktemp()))
        service = service_for_pool(self, pool)
        volume = service.get(u"myvolumename")

        d = pool.create(volume)

        def created_filesystems(filesystem):
            # This would error if writing was not possible:
            filesystem.get_path().child(b"text").setContent(b"hello")
        d.addCallback(created_filesystems)
        return d

    def assertReadOnly(self, path):
        """
        Assert writes are not possible to the given filesystem path.

        :param FilePath path: Directory which ought to be read-only.
        """
        exc = self.assertRaises(OSError,
                                path.child(b"text").setContent, b"hello")
        self.assertEqual(exc.args[0], errno.EROFS)

    def test_remotely_owned_created_readonly(self):
        """
        A filesystem which is created for a remotely owned volume is not
        writeable.
        """
        pool = StoragePool(reactor, create_zfs_pool(self),
                           FilePath(self.mktemp()))
        service = service_for_pool(self, pool)
        volume = Volume(uuid=u"remoteone", name=u"vol", service=service)

        d = pool.create(volume)

        def created_filesystems(filesystem):
            self.assertReadOnly(filesystem.get_path())
        d.addCallback(created_filesystems)
        return d

    def test_written_created_readonly(self):
        """
        A filesystem which is received from a remote filesystem (which is
        writable in its origin pool) is not writeable.
        """
        def fixture(_):
            return StoragePool(reactor, create_zfs_pool(self),
                               FilePath(self.mktemp()))
        d = create_and_copy(self, fixture)

        def got_volumes(copied):
            self.assertReadOnly(copied.to_volume.get_filesystem().get_path())
        d.addCallback(got_volumes)
        return d

    def test_owner_change_to_locally_becomes_writeable(self):
        """
        A filesystem which was previously remotely owned and is now locally
        owned becomes writeable.
        """
        pool = StoragePool(reactor, create_zfs_pool(self),
                           FilePath(self.mktemp()))
        service = service_for_pool(self, pool)
        local_volume = service.get(u"myvolumename")
        remote_volume = Volume(uuid=u"other-uuid", name=u"volume",
                               service=service)

        d = pool.create(remote_volume)

        def created_filesystems(ignored):
            return pool.change_owner(remote_volume, local_volume)
        d.addCallback(created_filesystems)

        def changed_owner(filesystem):
            # This would error if writing was not possible:
            filesystem.get_path().child(b"text").setContent(b"hello")
        d.addCallback(changed_owner)
        return d

    def test_owner_change_to_remote_becomes_readonly(self):
        """
        A filesystem which was previously locally owned and is now remotely
        owned becomes unwriteable.
        """
        pool = StoragePool(reactor, create_zfs_pool(self),
                           FilePath(self.mktemp()))
        service = service_for_pool(self, pool)
        local_volume = service.get(u"myvolumename")
        remote_volume = Volume(uuid=u"other-uuid", name=u"volume",
                               service=service)

        d = pool.create(local_volume)

        def created_filesystems(ignored):
            return pool.change_owner(local_volume, remote_volume)
        d.addCallback(created_filesystems)

        def changed_owner(filesystem):
            self.assertReadOnly(filesystem.get_path())
        d.addCallback(changed_owner)
        return d
