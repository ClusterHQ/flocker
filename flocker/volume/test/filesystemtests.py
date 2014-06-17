# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Generic tests for filesystem APIs.

A "fixture" is a 1-argument callable that takes a :class:`unittest.TestCase`
instance as its first argument and returns some object to be used in a test.
"""

from __future__ import absolute_import

import os
from datetime import datetime

from zope.interface.verify import verifyObject

from twisted.trial.unittest import TestCase
from twisted.internet.defer import gatherResults
from twisted.python.filepath import FilePath

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
            def created_filesystem(filesystem):
                self.assertTrue(verifyObject(IFilesystem, filesystem))
            d.addCallback(created_filesystem)
            return d

        def test_two_names_create_different_filesystems(self):
            """Two calls to ``create()`` with different volume names return
            different filesystems.
            """
            pool = fixture(self)
            volume = Volume(uuid=u"my-uuid", name=u"myvolumename", _pool=pool)
            volume2 = Volume(uuid=u"my-uuid", name=u"myvolumename2", _pool=pool)
            d = gatherResults([pool.create(volume), pool.create(volume2)])
            def created_filesystems(filesystems):
                first, second = filesystems
                # Thanks Python! *Obviously* you should have two code paths
                # for equality to work correctly.
                self.assertTrue(first != second)
                self.assertFalse(first == second)
            d.addCallback(created_filesystems)
            return d

        def test_two_uuid_create_different_filesystems(self):
            """Two calls to ``create()`` with different volume manager UUIDs
            return different filesystems.
            """
            pool = fixture(self)
            volume = Volume(uuid=u"my-uuid", name=u"myvolumename", _pool=pool)
            volume2 = Volume(uuid=u"my-uuid2", name=u"myvolumename", _pool=pool)
            d = gatherResults([pool.create(volume), pool.create(volume2)])
            def created_filesystems(filesystems):
                first, second = filesystems
                # Thanks Python! *Obviously* you should have two code paths
                # for equality to work correctly.
                self.assertTrue(first != second)
                self.assertFalse(first == second)
            d.addCallback(created_filesystems)
            return d

        def test_get_filesystem(self):
            """``get()`` returns the same :class:`IFilesystem` provider as the
            earlier created one."""
            pool = fixture(self)
            volume = Volume(uuid=u"my-uuid", name=u"myvolumename", _pool=pool)
            d = pool.create(volume)
            def created_filesystem(filesystem):
                filesystem2 = pool.get(volume)
                self.assertTrue(filesystem == filesystem2)
                self.assertFalse(filesystem != filesystem2)
            d.addCallback(created_filesystem)
            return d

        def test_mountpoint(self):
            """The volume's filesystem has a mountpoint which is a directory."""
            pool = fixture(self)
            volume = Volume(uuid=u"my-uuid", name=u"myvolumename", _pool=pool)
            d = pool.create(volume)
            def created_filesystem(filesystem):
                self.assertTrue(filesystem.get_path().isdir())
            d.addCallback(created_filesystem)
            return d

        def test_two_volume_mountpoints_different(self):
            """Each volume has its own mountpoint."""
            pool = fixture(self)
            volume = Volume(uuid=u"my-uuid", name=u"myvolumename", _pool=pool)
            volume2 = Volume(uuid=u"my-uuid", name=u"myvolumename2", _pool=pool)
            d = gatherResults([pool.create(volume), pool.create(volume2)])
            def created_filesystems(filesystems):
                first, second = filesystems
                self.assertNotEqual(first.get_path(),
                                    second.get_path())
            d.addCallback(created_filesystems)
            return d

        def copy(self, from_volume, to_volume):
            """Copy contents of one volume to another.

            :param Volume from_volume: Volume to read from.
            :param Volume to_volume: Volume to write to.
            """
            from_filesystem = from_volume.get_filesystem()
            to_filesystem = to_volume.get_filesystem()
            with from_filesystem.reader() as reader:
                with to_filesystem.writer() as writer:
                    for chunk in iter(lambda: reader.read(4096), b""):
                        writer.write(chunk)

        def process_fds(self):
            """Return the number of file descriptors opened by this process."""
            path = FilePath(b"/proc").descendant(
                [b"%d" % (os.getpid(),), b"fds"])
            return len(path.children())

        def test_reader_cleanup(self):
            """The reader does not leave any open file descriptors behind."""
            pool = fixture(self)
            volume = Volume(uuid=u"my-uuid", name=u"myvolumename", _pool=pool)
            d = pool.create(volume)
            def created_filesystem(filesystem):
                fds = self.process_fds()
                with filesystem.reader():
                    pass
                self.assertEqual(fds, self.process_fds())
            d.addCallback(created_filesystem)
            return d

        def test_writer_cleanup(self):
            """The writer does not leave any open file descriptors behind."""
            pool = fixture(self)
            volume = Volume(uuid=u"my-uuid", name=u"myvolumename", _pool=pool)
            d = pool.create(volume)
            def created_filesystem(filesystem):
                with filesystem.reader() as reader:
                    data = reader.read()
                fds = self.process_fds()
                with filesystem.writer() as writer:
                    writer.write(data)
                self.assertEqual(fds, self.process_fds())
            d.addCallback(created_filesystem)
            return d

        def assertVolumesEqual(self, first, second):
            """Assert that two filesystems have the same contents.

            :param Volume first: First volume.
            :param Volume second: Second volume.
            """
            first = first.get_filesystem().get_path()
            second = second.get_filesystem().get_path()

            def get_contents(path):
                result = {}
                for child in path.children():
                    if child.isdirectory():
                        value = get_contents(child)
                    else:
                        value = child.getContent()
                    result[child.basename()] = value
                return result
            self.assertEqual(get_contents(first), get_contents(second))

        def test_write_new_fileystem(self):
            """Writing the contents of one pool's filesystem to another pool's
            filesystem creates that filesystem with the given contents.
            """
            pool = fixture(self)
            volume = Volume(uuid=u"my-uuid", name=u"myvolumename", _pool=pool)
            pool2 = fixture(self)
            volume2 = Volume(uuid=u"my-uuid", name=u"myvolumename", _pool=pool2)

            d = pool.create(volume)
            def created_filesystem(filesystem):
                path = filesystem.get_path()
                path.child(b"file").setContent(b"some bytes")
                path.child("directory").makedirs()
                self.copy(volume, volume2)
                self.assertVolumesEqual(volume, volume2)
            d.addCallback(created_filesystem)
            return d

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
