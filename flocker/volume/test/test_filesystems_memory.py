# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for :module:`flocker.filesystems.memory`.
"""

from __future__ import absolute_import

from twisted.internet.defer import succeed, fail
from twisted.python.filepath import FilePath

from .filesystemtests import (
    make_ifilesystemsnapshots_tests, make_istoragepool_tests,
)
from ..filesystems.memory import (
    CannedFilesystemSnapshots, FilesystemStoragePool,
    DirectoryFilesystem,
)
from ...testtools import (
    TestCase, assert_equal_comparison, assert_not_equal_comparison
)


class IFilesystemSnapshotsTests(make_ifilesystemsnapshots_tests(
    lambda test_case: CannedFilesystemSnapshots(
        [succeed(None), succeed(None)]))):
    """``IFilesystemSnapshotsTests`` for in-memory filesystem."""


class CannedFilesystemSnapshotsTests(TestCase):
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
        FilesystemStoragePool(FilePath(test_case.mktemp())),
        lambda fs: CannedFilesystemSnapshots([succeed(None), succeed(None)]))):
    """``IStoragePoolTests`` for fake storage pool."""


class DirectoryFilesystemTests(TestCase):
    """
    Direct tests for ``FilesystemStoragePool``\ 's ``IFilesystem``
    implementation, ``DirectoryFilesystem``.
    """
    def test_equality(self):
        """
        Two ``DirectoryFilesystem`` instances are equal if they refer to the
        same directory.
        """
        path = FilePath(b"/foo/bar")
        assert_equal_comparison(
            self,
            DirectoryFilesystem(path=path, size=123),
            DirectoryFilesystem(path=path, size=321)
        )

    def test_inequality(self):
        """
        Two ``DirectoryFilesystem`` instances are not equal if they refer to
        different directories.
        """
        assert_not_equal_comparison(
            self,
            DirectoryFilesystem(path=FilePath(b"/foo/bar"), size=123),
            DirectoryFilesystem(path=FilePath(b"/foo/baz"), size=123)
        )

    def test_repr(self):
        """
        A ``DirectoryFilesystem`` instance represents itself as a string
        including the type name and the values of its attributes.
        """
        self.assertEqual(
            "<DirectoryFilesystem(path=FilePath('/foo/bar'), size=123)>",
            repr(DirectoryFilesystem(
                path=FilePath(b"/foo/bar"), size=123))
        )
