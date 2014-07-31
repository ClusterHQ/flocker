# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Testing utilities provided by ``flocker.volume``.
"""

import os
import uuid
import subprocess
from unittest import SkipTest

from twisted.python.filepath import FilePath
from twisted.internet.task import Clock

from .service import VolumeService
from .filesystems.memory import FilesystemStoragePool


def create_volume_service(test):
    """
    Create a new ``VolumeService`` suitable for use in unit tests.

    :param TestCase test: A unit test which will shut down the service
        when done.

    :return: The ``VolumeService`` created.
    """
    service = VolumeService(FilePath(test.mktemp()),
                            FilesystemStoragePool(FilePath(test.mktemp())),
                            reactor=Clock())
    service.startService()
    test.addCleanup(service.stopService)
    return service


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
