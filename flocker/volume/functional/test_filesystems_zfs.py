# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""Functional tests for ZFS filesystem implementation.

Further coverage is provided in
:module:`flocker.volume.test.test_filesystems_zfs`.
"""

import os
import subprocess
import uuid

from twisted.internet import reactor
from twisted.trial.unittest import SkipTest, TestCase
from twisted.python.filepath import FilePath

from ..test.filesystemtests import (
    make_ifilesystemsnapshots_tests, make_istoragepool_tests,
    )
from ..filesystems.zfs import (
    ZFSSnapshots, Filesystem, StoragePool, volume_to_dataset,
    )
from ..service import Volume


def create_zfs_pool(test_case):
    """Create a new ZFS pool, then delete it after the test is over.

    :param test_case: A ``unittest.TestCase``.

    :return: The pool's name as ``bytes``.
    """
    if os.getuid() != 0:
        raise SkipTest("Functional tests must run as root.")

    pool_name = b"testpool_%s" % (uuid.uuid4(),)
    pool_path = FilePath(test_case.mktemp())
    mount_path = FilePath(test_case.mktemp())
    with pool_path.open("wb") as f:
        f.truncate(100 * 1024 * 1024)
    test_case.addCleanup(pool_path.remove)
    subprocess.check_call([b"zpool", b"create", b"-m", mount_path.path,
                           pool_name, pool_path.path])
    test_case.addCleanup(subprocess.check_call,
                         [b"zpool", b"destroy", pool_name])
    return pool_name


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
                         b"my-uuid.myvolumename.trunk")


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
