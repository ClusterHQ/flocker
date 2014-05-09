# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Functional tests for ZFS filesystem implementation.

Further coverage is provided in
:module:`flocker.test.test_filesystems_zfs`.
"""

import os
import tempfile
import subprocess
import uuid
from twisted.internet import reactor

from ..test.filesystemtests import makeIFilesystemSnapshotsTests
from ..filesystems.zfs import ZFSSnapshots, Filesystem


def createZFSPool(testCase):
    """
    Create a new ZFS pool, then delete it after the test is over.

    :param testCase: A ``unittest.TestCase``.

    :return: A :class:`Filesystem` instance.
    """
    poolName = "testpool_%s" % (uuid.uuid4(),)
    poolPath = tempfile.mktemp()
    mountPath = tempfile.mktemp()
    subprocess.check_call([b"dd", b"if=/dev/zero", b"of=%s" % (poolPath),
                           b"count=200000"])
    testCase.addCleanup(os.remove, poolPath)
    subprocess.check_call([b"zpool", b"create", b"-m", mountPath, poolName,
                           poolPath])
    testCase.addCleanup(subprocess.check_call, [b"zpool", b"destroy", poolName])
    return Filesystem(poolName)



IFilesystemSnapshotsTests = makeIFilesystemSnapshotsTests(
    lambda testCase: ZFSSnapshots(reactor, createZFSPool(testCase)))
