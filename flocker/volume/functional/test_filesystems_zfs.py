# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""Functional tests for ZFS filesystem implementation.

Further coverage is provided in
:module:`flocker.volume.test.test_filesystems_zfs`.
"""

import os
import subprocess
import uuid

from twisted.internet import reactor
from twisted.trial.unittest import SkipTest
from twisted.python.filepath import FilePath

from ..test.filesystemtests import (
    make_ifilesystemsnapshots_tests, make_istoragepool_tests,
    )
from ..filesystems.zfs import ZFSSnapshots, Filesystem, StoragePool


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
