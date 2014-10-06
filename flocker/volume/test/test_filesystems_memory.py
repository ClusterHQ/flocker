# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for :module:`flocker.filesystems.memory`.
"""

from __future__ import absolute_import

from twisted.internet.defer import succeed, fail
from twisted.trial.unittest import SynchronousTestCase
from twisted.python.filepath import FilePath

from .filesystemtests import (
    make_ifilesystemsnapshots_tests, make_istoragepool_tests,
    )
from ..filesystems.memory import (
    CannedFilesystemSnapshots, FilesystemStoragePool,
    )


class IFilesystemSnapshotsTests(make_ifilesystemsnapshots_tests(
    lambda test_case: CannedFilesystemSnapshots(
        [succeed(None), succeed(None)]))):
    """``IFilesystemSnapshotsTests`` for in-memory filesystem."""


class CannedFilesystemSnapshotsTests(SynchronousTestCase):
    """
    Additional test cases for CannedFilesystemSnapshots.
    """
    def test_failed(self):
        """
        Failed snapshots are not added to the list of snapshots.
        """
        snapshotter = CannedFilesystemSnapshots([fail(RuntimeError())])
        self.failureResultOf(snapshotter.create(b"name"))
        self.assertEqual(self.successResultOf(snapshotter.list()), [])

    def test_too_many(self):
        """
        Creating more than the canned number of snapshots results in an error.

        This is useful for unit testing.
        """
        snapshotter = CannedFilesystemSnapshots([])
        self.assertRaises(IndexError, snapshotter.create, b"first")


class IStoragePoolTests(make_istoragepool_tests(
    lambda test_case:
        FilesystemStoragePool(FilePath(test_case.mktemp())))):
    """``IStoragePoolTests`` for fake storage pool."""
