# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""Functional tests for ZFS filesystem implementation.

Further coverage is provided in
:module:`flocker.volume.test.test_filesystems_zfs`.
"""

import os
import tempfile
import subprocess
import uuid

from twisted.internet import reactor
from twisted.trial.unittest import SkipTest

from ..test.filesystemtests import makeIFilesystemSnapshotsTests
from ..filesystems.zfs import ZFSSnapshots, Filesystem


def create_zfs_pool(test_case):
    """Create a new ZFS pool, then delete it after the test is over.

    :param test_case: A ``unittest.TestCase``.

    :return: A :class:`Filesystem` instance.
    """
    if os.getuid() != 0:
        raise SkipTest("Functional tests must run as root.")

    pool_name = "testpool_%s" % (uuid.uuid4(),)
    pool_path = tempfile.mktemp()
    mount_path = tempfile.mktemp()
    subprocess.check_call([b"dd", b"if=/dev/zero", b"of=%s" % (pool_path),
                           b"count=200000"])
    test_case.addCleanup(os.remove, pool_path)
    subprocess.check_call([b"zpool", b"create", b"-m", mount_path, pool_name,
                           pool_path])
    test_case.addCleanup(subprocess.check_call,
                        [b"zpool", b"destroy", pool_name])
    return Filesystem(pool_name)


IFilesystemSnapshotsTests = makeIFilesystemSnapshotsTests(
    lambda test_case: ZFSSnapshots(reactor, create_zfs_pool(test_case)))
