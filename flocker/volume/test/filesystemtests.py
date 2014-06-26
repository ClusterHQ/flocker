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

from ...testtools import assertNoFDsLeaked

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
        Tests for :class:`IFilesystemSnapshots` implementors.

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


def copy(from_volume, to_volume):
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
            volume2 = Volume(uuid=u"my-uuid", name=u"myvolumename2",
                             _pool=pool)
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
            volume2 = Volume(uuid=u"my-uuid2", name=u"myvolumename",
                             _pool=pool)
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
            """The volume's filesystem has a mountpoint which is a
            directory."""
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
            volume2 = Volume(uuid=u"my-uuid", name=u"myvolumename2",
                             _pool=pool)
            d = gatherResults([pool.create(volume), pool.create(volume2)])
            def created_filesystems(filesystems):
                first, second = filesystems
                self.assertNotEqual(first.get_path(),
                                    second.get_path())
            d.addCallback(created_filesystems)
            return d

        def test_reader_cleanup(self):
            """The reader does not leave any open file descriptors behind."""
            pool = fixture(self)
            volume = Volume(uuid=u"my-uuid", name=u"myvolumename", _pool=pool)
            d = pool.create(volume)
            def created_filesystem(filesystem):
                with assertNoFDsLeaked(self):
                    with filesystem.reader():
                        pass
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
                with assertNoFDsLeaked(self):
                    with filesystem.writer() as writer:
                        writer.write(data)
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
                    if child.isdir():
                        value = get_contents(child)
                    else:
                        value = child.getContent()
                    result[child.basename()] = value
                return result
            self.assertEqual(get_contents(first), get_contents(second))

        def create_and_copy(self):
            """Create a volume's filesystem on one pool, copy to another pool.

            :return: ``Deferred`` that fires with the two volumes, from and to.
            """
            pool = fixture(self)
            volume = Volume(uuid=u"my-uuid", name=u"myvolumename", _pool=pool)
            pool2 = fixture(self)
            volume2 = Volume(uuid=u"my-uuid", name=u"myvolumename", _pool=pool2)

            d = gatherResults([pool.create(volume), pool2.create(volume2)])
            def created_filesystem(results):
                filesystem, filesystem2 = results
                path = filesystem.get_path()
                path.child(b"file").setContent(b"some bytes")
                path.child(b"directory").makedirs()
                copy(volume, volume2)
                return (volume, volume2)
            d.addCallback(created_filesystem)
            return d

        def test_write_new_filesystem(self):
            """Writing the contents of one pool's filesystem to another pool's
            filesystem creates that filesystem with the given contents.
            """
            d = self.create_and_copy()
            def got_volumes((volume, volume2)):
                self.assertVolumesEqual(volume, volume2)
            d.addCallback(got_volumes)
            return d

        def test_write_update_to_unchanged_filesystem(self):
            """Writing an update of the contents of one pool's filesystem to
            another pool's filesystem that was previously created this way but
            is unchanged updates its contents.
            """
            d = self.create_and_copy()
            def got_volumes((volume, volume2)):
                path = volume.get_filesystem().get_path()
                path.child(b"anotherfile").setContent(b"hello")
                path.child(b"file").remove()
                copy(volume, volume2)
                self.assertVolumesEqual(volume, volume2)
            d.addCallback(got_volumes)
            return d

        def test_write_update_to_changed_filesystem(self):
            """Writing an update of the contents of one pool's filesystem to
            another pool's filesystem that was previously created this way and
            was since changed drops any changes and updates its contents to
            the sender's.
            """
            d = self.create_and_copy()
            def got_volumes((volume, volume2)):
                # Mutate the second volume's filesystem:
                path2 = volume2.get_filesystem().get_path()
                path2.child(b"extra").setContent(b"lalala")

                # Writing from first volume to second volume should revert
                # any changes to the second volume:
                path = volume.get_filesystem().get_path()
                path.child(b"anotherfile").setContent(b"hello")
                path.child(b"file").remove()
                copy(volume, volume2)
                self.assertVolumesEqual(volume, volume2)
            d.addCallback(got_volumes)
            return d

        def test_multiple_writes(self):
            """Writing the same contents to a filesystem twice does not result
            in an error.
            """
            d = self.create_and_copy()
            def got_volumes((volume, volume2)):
                copy(volume, volume2)
                self.assertVolumesEqual(volume, volume2)
            d.addCallback(got_volumes)
            return d

        def test_exception_passes_through_read(self):
            """If an exception is raised in the context of the reader, it is not
            swallowed."""
            pool = fixture(self)
            volume = Volume(uuid=u"my-uuid", name=u"myvolumename", _pool=pool)
            d = pool.create(volume)
            def created_filesystem(filesystem):
                with filesystem.reader():
                    raise RuntimeError("ONO")
            d.addCallback(created_filesystem)
            return self.assertFailure(d, RuntimeError)

        def test_exception_passes_through_write(self):
            """If an exception is raised in the context of the writer, it is not
            swallowed."""
            pool = fixture(self)
            volume = Volume(uuid=u"my-uuid", name=u"myvolumename", _pool=pool)
            d = pool.create(volume)
            def created_filesystem(filesystem):
                with filesystem.writer():
                    raise RuntimeError("ONO")
            d.addCallback(created_filesystem)
            return self.assertFailure(d, RuntimeError)

        def test_exception_cleanup_through_read(self):
            """If an exception is raised in the context of the reader, no
            filedescriptors are leaked."""
            pool = fixture(self)
            volume = Volume(uuid=u"my-uuid", name=u"myvolumename", _pool=pool)
            d = pool.create(volume)
            def created_filesystem(filesystem):
                with assertNoFDsLeaked(self):
                    try:
                        with filesystem.reader():
                            raise RuntimeError("ONO")
                    except RuntimeError:
                        pass
            d.addCallback(created_filesystem)
            return d

        def test_exception_cleanup_through_write(self):
            """If an exception is raised in the context of the writer, no
            filedescriptors are leaked."""
            pool = fixture(self)
            volume = Volume(uuid=u"my-uuid", name=u"myvolumename", _pool=pool)
            d = pool.create(volume)
            def created_filesystem(filesystem):
                with assertNoFDsLeaked(self):
                    try:
                        with filesystem.writer():
                            raise RuntimeError("ONO")
                    except RuntimeError:
                        pass
            d.addCallback(created_filesystem)
            return d

        def test_exception_aborts_write(self):
            """If an exception is raised in the context of the writer, no
            changes are made to the filesystem."""
            d = self.create_and_copy()

            def got_volumes((volume, volume2)):
                from_filesystem = volume.get_filesystem()
                to_filesystem = volume2.get_filesystem()
                try:
                    with from_filesystem.reader():
                        with to_filesystem.writer():
                            raise ZeroDivisionError()
                except ZeroDivisionError:
                    pass
                self.assertVolumesEqual(volume, volume2)
            d.addCallback(got_volumes)
            return d

        def test_garbage_in_write(self):
            """If garbage is written to the writer, no changes are made to the
            filesystem."""
            d = self.create_and_copy()

            def got_volumes((volume, volume2)):
                to_filesystem = volume2.get_filesystem()
                with to_filesystem.writer() as writer:
                    writer.write(b"NOT A REAL THING")
                self.assertVolumesEqual(volume, volume2)
            d.addCallback(got_volumes)
            return d

        def test_enumerate_no_filesystems(self):
            """Lacking any filesystems, ``enumerate()`` returns an empty
            result."""
            pool = fixture(self)
            enumerating = pool.enumerate()
            enumerating.addCallback(self.assertEqual, set())
            return enumerating

        def test_enumerate_some_filesystems(self):
            """
            The ``IStoragePool.enumerate`` implementation returns a
            ``Deferred`` that fires with a ``set`` of ``IFilesystem``
            providers, one for each filesystem which has been created in that
            pool.
            """
            pool = fixture(self)
            volume = Volume(uuid=u"my-uuid", name=u"name", _pool=pool)
            volume2 = Volume(uuid=u"my-uuid", name=u"name2", _pool=pool)
            creating = gatherResults([
                pool.create(volume), pool.create(volume2)])

            def created(ignored):
                return pool.enumerate()
            enumerating = creating.addCallback(created)

            def enumerated(result):
                expected = {volume.get_filesystem(), volume2.get_filesystem()}
                self.assertEqual(expected, result)
            return enumerating.addCallback(enumerated)

        def test_consistent_naming_pattern(self):
            """``IFilesystem.get_path().basename()`` has a consistent naming
            pattern. This test should be removed as part of:
                https://github.com/hybridlogic/flocker/issues/78"""
            pool = fixture(self)
            uuid = u"my-uuid"
            volume_name = u"myvolumename"
            volume = Volume(uuid=uuid, name=volume_name, _pool=pool)
            d = pool.create(volume)

            def createdFilesystem(filesystem):
                name = filesystem.get_path().basename()
                expected = u"{uuid}.{name}".format(uuid=uuid, name=volume_name)
                self.assertEqual(name, expected)
            d.addCallback(createdFilesystem)
            return d

    return IStoragePoolTests
