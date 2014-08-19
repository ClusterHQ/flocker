# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""Functional tests for ZFS filesystem implementation.

Further coverage is provided in
:module:`flocker.volume.test.test_filesystems_zfs`.
"""

import subprocess

from twisted.internet import reactor
from twisted.trial.unittest import TestCase
from twisted.python.filepath import FilePath

from ..test.filesystemtests import (
    make_ifilesystemsnapshots_tests, make_istoragepool_tests,
    )
from ..filesystems.zfs import (
    ZFSSnapshots, Filesystem, StoragePool, volume_to_dataset,
    )
from ..service import Volume
from ..testtools import create_zfs_pool


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
        volume = Volume(uuid=u"my-uuid", name=u"myvolumename", _pool=None)
        self.assertEqual(volume_to_dataset(volume),
                         b"my-uuid.myvolumename")


class StoragePoolTests(TestCase):
    """ZFS-specific ``StoragePool`` tests."""

    def test_mount_root(self):
        """Mountpoints are children of the mount root."""
        mount_root = FilePath(self.mktemp())
        pool = StoragePool(reactor, create_zfs_pool(self), mount_root)
        volume = Volume(uuid=u"my-uuid", name=u"myvolumename", _pool=pool)

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
        volume = Volume(uuid=u"my-uuid", name=u"myvolumename", _pool=pool)

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
        volume = Volume(uuid=u"my-uuid", name=u"myvolumename", _pool=pool)

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
        volume = Volume(uuid=u"my-uuid", name=u"volume", _pool=pool)
        new_volume = Volume(uuid=u"other-uuid", name=u"volume", _pool=pool)
        original_mount = volume.get_filesystem().get_path()
        d = pool.create(volume)

        def created_filesystems(igonred):
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
