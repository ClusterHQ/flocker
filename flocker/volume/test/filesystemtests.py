# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Generic tests for filesystem APIs.

A "fixture" is a 1-argument callable that takes a :class:`unittest.TestCase`
instance as its first argument and returns some object to be used in a test.
"""

from __future__ import absolute_import

from datetime import datetime

from zope.interface.verify import verifyObject

from twisted.trial.unittest import TestCase
from twisted.internet.defer import gatherResults

from pytz import UTC

from ..filesystems.interfaces import (
    IFilesystemSnapshots, IStoragePool, IFilesystem,
    )
from ..snapshots import SnapshotName
from ..service import Volume


def make_ifilesystemsnapshots_tests(fixture):
    """
    Create a TestCase for IFilesystemSnapshots.

    :param fixture: A fixture that returns a :class:`IFilesystemSnapshots`
        provider.
    """
    class IFilesystemSnapshotsTests(TestCase):
        """
        Tests for :class:`IFilesystemSnapshotsTests`.

        These are functional tests if run against real filesystems.
        """
        def test_interface(self):
            """
            The tested object provides :class:`IFilesystemSnapshots`.
            """
            fsSnapshots = fixture(self)
            self.assertTrue(verifyObject(IFilesystemSnapshots, fsSnapshots))


        def test_created(self):
            """
            Snapshots created with ``create()`` are listed in that order in
            ``list()``.
            """
            fsSnapshots = fixture(self)
            first = SnapshotName(datetime.now(UTC), b"first")
            second = SnapshotName(datetime.now(UTC), b"second")
            d = fsSnapshots.create(first)
            d.addCallback(lambda _: fsSnapshots.create(second))
            d.addCallback(lambda _: fsSnapshots.list())
            d.addCallback(self.assertEqual, [first, second])
            return d
    return IFilesystemSnapshotsTests


def make_istoragepool_tests(fixture):
    """Create a TestCase for IStoragePool.

    :param fixture: A fixture that returns a :class:`IStoragePool`
        provider, and which is assumed to clean up after itself when the
        test is over.
    """
    class IStoragePoolTests(TestCase):
        """Tests for a :class:`IStoragePool` implementation and its
        corresponding :class:`IFilesystem` implementation.

        These are functional tests if run against real filesystems.
        """
        def test_interface(self):
            """The tested object provides :class:`IStoragePool`."""
            pool = fixture(self)
            self.assertTrue(verifyObject(IStoragePool, pool))

        def test_create_filesystem(self):
            """``create()`` returns a :class:`IFilesystem` provider."""
            pool = fixture(self)
            volume = Volume(uuid=u"my-uuid", name=u"myvolumename", _pool=pool)
            d = pool.create(volume)
            def createdFilesystem(filesystem):
                self.assertTrue(verifyObject(IFilesystem, filesystem))
            d.addCallback(createdFilesystem)
            return d

        def test_two_names_create_different_filesystems(self):
            """Two calls to ``create()`` with different volume names return
            different filesystems.
            """
            pool = fixture(self)
            volume = Volume(uuid=u"my-uuid", name=u"myvolumename", _pool=pool)
            volume2 = Volume(uuid=u"my-uuid", name=u"myvolumename2", _pool=pool)
            d = gatherResults([pool.create(volume), pool.create(volume2)])
            def createdFilesystems(filesystems):
                first, second = filesystems
                # Thanks Python! *Obviously* you should have two code paths
                # for equality to work correctly.
                self.assertTrue(first != second)
                self.assertFalse(first == second)
            d.addCallback(createdFilesystems)
            return d

        def test_two_uuid_create_different_filesystems(self):
            """Two calls to ``create()`` with different volume manager UUIDs
            return different filesystems.
            """
            pool = fixture(self)
            volume = Volume(uuid=u"my-uuid", name=u"myvolumename", _pool=pool)
            volume2 = Volume(uuid=u"my-uuid2", name=u"myvolumename", _pool=pool)
            d = gatherResults([pool.create(volume), pool.create(volume2)])
            def createdFilesystems(filesystems):
                first, second = filesystems
                # Thanks Python! *Obviously* you should have two code paths
                # for equality to work correctly.
                self.assertTrue(first != second)
                self.assertFalse(first == second)
            d.addCallback(createdFilesystems)
            return d

        def test_get_filesystem(self):
            """``get()`` returns the same :class:`IFilesystem` provider as the
            earlier created one."""
            pool = fixture(self)
            volume = Volume(uuid=u"my-uuid", name=u"myvolumename", _pool=pool)
            d = pool.create(volume)
            def createdFilesystem(filesystem):
                filesystem2 = pool.get(volume)
                self.assertTrue(filesystem == filesystem2)
                self.assertFalse(filesystem != filesystem2)
            d.addCallback(createdFilesystem)
            return d

        def test_mountpoint(self):
            """The volume's filesystem has a mountpoint which is a directory."""
            pool = fixture(self)
            volume = Volume(uuid=u"my-uuid", name=u"myvolumename", _pool=pool)
            d = pool.create(volume)
            def createdFilesystem(filesystem):
                self.assertTrue(filesystem.get_path().isdir())
            d.addCallback(createdFilesystem)
            return d

        def test_two_volume_mountpoints_different(self):
            """Each volume has its own mountpoint."""
            pool = fixture(self)
            volume = Volume(uuid=u"my-uuid", name=u"myvolumename", _pool=pool)
            volume2 = Volume(uuid=u"my-uuid", name=u"myvolumename2", _pool=pool)
            d = gatherResults([pool.create(volume), pool.create(volume2)])
            def createdFilesystems(filesystems):
                first, second = filesystems
                self.assertNotEqual(first.get_path(),
                                    second.get_path())
            d.addCallback(createdFilesystems)
            return d

        def test_reader_cleanup(self):
            """The reader does not leave any open file descriptors behind."""

        def test_writer_cleanup(self):
            """The writer does not leave any open file descriptors behind."""

        def test_write_new_fileystem(self):
            """Writing the contents of one pool's filesystem to another pool's
            filesystem creates that filesystem with the given contents.
            """

        def test_write_update_to_unchanged_filesystem(self):
            """Writing an update of the contents of one pool's filesystem to
            another pool's filesystem that was previously created this way but
            is unchanged updates its contents.
            """

        def test_write_update_to_changed_filesystem(self):
            """Writing an update of the contents of one pool's filesystem to
            another pool's filesystem that was previously created this way and
            was since changed drops any changes and updates its contents to
            the sender's.
            """

        def test_multiple_writes(self):
            """Writing the same contents to a filesystem twice does not result
            in an error
            """

    return IStoragePoolTests
