# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Generic tests for filesystem APIs.

A "fixture" is a 1-argument callable that takes a :class:`unittest.TestCase`
instance as its first argument and returns some object to be used in a test.
"""

from __future__ import absolute_import

from datetime import datetime

from characteristic import attributes
from zope.interface.verify import verifyObject

from twisted.trial.unittest import TestCase
from twisted.internet.defer import gatherResults
from twisted.application.service import IService

from pytz import UTC

from ...testtools import assertNoFDsLeaked
from ..testtools import service_for_pool

from ..filesystems.interfaces import (
    IFilesystemSnapshots, IStoragePool, IFilesystem,
    FilesystemAlreadyExists,
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


@attributes(["from_volume", "to_volume"])
class CopyVolumes(object):
    """A pair of volumes that had data copied from one to the other.

    :ivar from_volume Volume: Volume data was copied from.
    :ivar to_volume Volume: Volume data was copied to.
    """


def create_and_copy(test, fixture):
    """
    Create a volume's filesystem on one pool, copy to another pool.

    :param TestCase test: A ``TestCase`` that will be the context for this
        operation.
    :param fixture: Callable that takes ``TestCase`` and returns a
        ``IStoragePool`` provider.

    :return: ``Deferred`` that fires with the two volumes in a
        ``CopyVolumes``.
    """
    pool = fixture(test)
    service = service_for_pool(test, pool)
    volume = service.get(u"myvolumename")
    pool2 = fixture(test)
    service2 = service_for_pool(test, pool2)
    volume2 = Volume(
        uuid=service.uuid,
        name=u"myvolumename",
        service=service2,
    )

    d = pool.create(volume)

    def created_filesystem(filesystem):
        path = filesystem.get_path()
        path.child(b"file").setContent(b"some bytes")
        path.child(b"directory").makedirs()
        copy(volume, volume2)
        return CopyVolumes(from_volume=volume, to_volume=volume2)
    d.addCallback(created_filesystem)
    return d


def assertVolumesEqual(test, first, second):
    """
    Assert that two filesystems have the same contents.

    :param TestCase test: A ``TestCase`` that will be the context for this
        operation.
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
    test.assertEqual(get_contents(first), get_contents(second))


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
            """
            The tested object provides :class:`IStoragePool`.
            """
            pool = fixture(self)
            self.assertTrue(verifyObject(IStoragePool, pool))

        def test_service(self):
            """
            The tested object provides :class:`IService`.
            """
            pool = fixture(self)
            self.assertTrue(verifyObject(IService, pool))

        def test_running(self):
            """
            The tested object is ``running`` after its ``startService`` method
            is called.
            """
            pool = fixture(self)
            pool.startService()
            self.assertTrue(pool.running)

        def test_create_filesystem(self):
            """
            ``create()`` returns a :class:`IFilesystem` provider.
            """
            pool = fixture(self)
            service = service_for_pool(self, pool)
            volume = service.get(u"myvolumename")
            d = pool.create(volume)

            def created_filesystem(filesystem):
                self.assertTrue(verifyObject(IFilesystem, filesystem))
            d.addCallback(created_filesystem)
            return d

        def test_two_names_create_different_filesystems(self):
            """
            Two calls to ``create()`` with different volume names return
            different filesystems.
            """
            pool = fixture(self)
            service = service_for_pool(self, pool)
            volume = service.get(u"myvolumename")
            volume2 = service.get(u"myvolumename2")
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
            """
            Two calls to ``create()`` with different volume manager UUIDs
            return different filesystems.
            """
            pool = fixture(self)
            service = service_for_pool(self, pool)
            volume = service.get(u"myvolumename")
            volume2 = service.get(u"myvolumename2")
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
            """
            ``get()`` returns the same :class:`IFilesystem` provider as the
            earlier created one.
            """
            pool = fixture(self)
            service = service_for_pool(self, pool)
            volume = service.get(u"myvolumename")
            d = pool.create(volume)

            def created_filesystem(filesystem):
                filesystem2 = pool.get(volume)
                self.assertTrue(filesystem == filesystem2)
                self.assertFalse(filesystem != filesystem2)
            d.addCallback(created_filesystem)
            return d

        def test_mountpoint(self):
            """
            The volume's filesystem has a mountpoint which is a directory.
            """
            pool = fixture(self)
            service = service_for_pool(self, pool)
            volume = service.get(u"myvolumename")
            d = pool.create(volume)

            def created_filesystem(filesystem):
                self.assertTrue(filesystem.get_path().isdir())
            d.addCallback(created_filesystem)
            return d

        def test_two_volume_mountpoints_different(self):
            """
            Each volume has its own mountpoint.
            """
            pool = fixture(self)
            service = service_for_pool(self, pool)
            volume = service.get(u"myvolumename")
            volume2 = service.get(u"myvolumename2")
            d = gatherResults([pool.create(volume), pool.create(volume2)])

            def created_filesystems(filesystems):
                first, second = filesystems
                self.assertNotEqual(first.get_path(),
                                    second.get_path())
            d.addCallback(created_filesystems)
            return d

        def test_reader_cleanup(self):
            """
            The reader does not leave any open file descriptors behind.
            """
            pool = fixture(self)
            service = service_for_pool(self, pool)
            volume = service.get(u"myvolumename")
            d = pool.create(volume)

            def created_filesystem(filesystem):
                with assertNoFDsLeaked(self):
                    with filesystem.reader():
                        pass
            d.addCallback(created_filesystem)
            return d

        def test_writer_cleanup(self):
            """
            The writer does not leave any open file descriptors behind.
            """
            pool = fixture(self)
            service = service_for_pool(self, pool)
            volume = service.get(u"myvolumename")
            d = pool.create(volume)

            def created_filesystem(filesystem):
                with filesystem.reader() as reader:
                    data = reader.read()
                with assertNoFDsLeaked(self):
                    with filesystem.writer() as writer:
                        writer.write(data)
            d.addCallback(created_filesystem)
            return d

        def test_write_new_filesystem(self):
            """
            Writing the contents of one pool's filesystem to another pool's
            filesystem creates that filesystem with the given contents.
            """
            d = create_and_copy(self, fixture)

            def got_volumes(copy_volumes):
                assertVolumesEqual(
                    self, copy_volumes.from_volume, copy_volumes.to_volume)
            d.addCallback(got_volumes)
            return d

        def test_write_update_to_unchanged_filesystem(self):
            """
            Writing an update of the contents of one pool's filesystem to
            another pool's filesystem that was previously created this way but
            is unchanged updates its contents.
            """
            d = create_and_copy(self, fixture)

            def got_volumes(copy_volumes):
                path = copy_volumes.from_volume.get_filesystem().get_path()
                path.child(b"anotherfile").setContent(b"hello")
                path.child(b"file").remove()
                copy(copy_volumes.from_volume, copy_volumes.to_volume)
                assertVolumesEqual(
                    self, copy_volumes.from_volume, copy_volumes.to_volume)
            d.addCallback(got_volumes)
            return d

        def test_multiple_writes(self):
            """
            Writing the same contents to a filesystem twice does not result in
            an error.
            """
            d = create_and_copy(self, fixture)

            def got_volumes(copied):
                volume, volume2 = copied.from_volume, copied.to_volume
                copy(volume, volume2)
                assertVolumesEqual(self, volume, volume2)
            d.addCallback(got_volumes)
            return d

        def test_exception_passes_through_read(self):
            """
            If an exception is raised in the context of the reader, it is not
            swallowed.
            """
            pool = fixture(self)
            service = service_for_pool(self, pool)
            volume = service.get(u"myvolumename")
            d = pool.create(volume)

            def created_filesystem(filesystem):
                with filesystem.reader():
                    raise RuntimeError("ONO")
            d.addCallback(created_filesystem)
            return self.assertFailure(d, RuntimeError)

        def test_exception_passes_through_write(self):
            """
            If an exception is raised in the context of the writer, it is not
            swallowed.
            """
            pool = fixture(self)
            service = service_for_pool(self, pool)
            volume = service.get(u"myvolumename")
            d = pool.create(volume)

            def created_filesystem(filesystem):
                with filesystem.writer():
                    raise RuntimeError("ONO")
            d.addCallback(created_filesystem)
            return self.assertFailure(d, RuntimeError)

        def test_exception_cleanup_through_read(self):
            """
            If an exception is raised in the context of the reader, no
            filedescriptors are leaked.
            """
            pool = fixture(self)
            service = service_for_pool(self, pool)
            volume = service.get(u"myvolumename")
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
            """
            If an exception is raised in the context of the writer, no
            filedescriptors are leaked.
            """
            pool = fixture(self)
            service = service_for_pool(self, pool)
            volume = service.get(u"myvolumename")
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
            """
            If an exception is raised in the context of the writer, no changes
            are made to the filesystem.
            """
            d = create_and_copy(self, fixture)

            def got_volumes(copied):
                volume, volume2 = copied.from_volume, copied.to_volume
                from_filesystem = volume.get_filesystem()
                path = from_filesystem.get_path()
                path.child(b"anotherfile").setContent(b"hello")

                to_filesystem = volume2.get_filesystem()
                try:
                    with from_filesystem.reader() as reader:
                        with to_filesystem.writer() as writer:
                            data = reader.read()
                            writer.write(data[1:])
                            raise ZeroDivisionError()
                except ZeroDivisionError:
                    pass
                to_path = volume2.get_filesystem().get_path()
                self.assertFalse(to_path.child(b"anotherfile").exists())
            d.addCallback(got_volumes)
            return d

        def test_garbage_in_write(self):
            """
            If garbage is written to the writer, no changes are made to the
            filesystem.
            """
            d = create_and_copy(self, fixture)

            def got_volumes(copied):
                volume, volume2 = copied.from_volume, copied.to_volume
                to_filesystem = volume2.get_filesystem()
                with to_filesystem.writer() as writer:
                    writer.write(b"NOT A REAL THING")
                assertVolumesEqual(self, volume, volume2)
            d.addCallback(got_volumes)
            return d

        def test_enumerate_no_filesystems(self):
            """
            Lacking any filesystems, ``enumerate()`` returns an empty result.
            """
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
            service = service_for_pool(self, pool)
            volume = service.get(u"name")
            volume2 = service.get(u"name2")
            creating = gatherResults([
                pool.create(volume), pool.create(volume2)])

            def created(ignored):
                return pool.enumerate()
            enumerating = creating.addCallback(created)

            def enumerated(result):
                expected = {volume.get_filesystem(), volume2.get_filesystem()}
                self.assertEqual(expected, result)
            return enumerating.addCallback(enumerated)

        def test_enumerate_spaces(self):
            """
            The ``IStoragePool.enumerate`` implementation doesn't return
            a ``Deferred`` that fires with a ``Failure`` if there is a
            filesystem with a space in it.
            """
            pool = fixture(self)
            service = service_for_pool(self, pool)
            volume = service.get(u"spaced name")
            creating = pool.create(volume)

            def created(ignored):
                return pool.enumerate()
            enumerating = creating.addCallback(created)

            def enumerated(result):
                expected = {volume.get_filesystem()}
                self.assertEqual(expected, result)
            return enumerating.addCallback(enumerated)

        def test_consistent_naming_pattern(self):
            """
            ``IFilesystem.get_path().basename()`` has a consistent naming
            pattern.

            This test should be removed as part of:
                https://github.com/ClusterHQ/flocker/issues/78
            """
            pool = fixture(self)
            volume_name = u"myvolumename"
            service = service_for_pool(self, pool)
            uuid = service.uuid
            volume = service.get(volume_name)
            d = pool.create(volume)

            def createdFilesystem(filesystem):
                name = filesystem.get_path().basename()
                expected = u"{uuid}.{name}".format(uuid=uuid, name=volume_name)
                self.assertEqual(name, expected)
            d.addCallback(createdFilesystem)
            return d

        def test_change_owner_creates_new(self):
            """
            ``IFilesystem.change_owner()`` exposes a filesystem for the new
            volume definition.
            """
            pool = fixture(self)
            service = service_for_pool(self, pool)
            volume = service.get(u"volume")
            new_volume = Volume(uuid=u"new-uuid", name=u"volume",
                                service=service)
            d = pool.create(volume)

            def created_filesystem(filesystem):
                old_path = filesystem.get_path()
                d = pool.change_owner(volume, new_volume)
                d.addCallback(lambda new_fs: (old_path, new_fs))
                return d
            d.addCallback(created_filesystem)

            def changed_owner((old_path, new_filesystem)):
                new_path = new_filesystem.get_path()
                self.assertNotEqual(old_path, new_path)
            d.addCallback(changed_owner)
            return d

        def test_change_owner_removes_old(self):
            """
            ``IStoragePool.change_owner()`` ensures the filesystem for the old
            volume definition no longer exists.
            """
            pool = fixture(self)
            service = service_for_pool(self, pool)
            volume = service.get(u"volume")
            new_volume = Volume(uuid=u"new-uuid", name=u"volume",
                                service=service)
            d = pool.create(volume)

            def created_filesystem(filesystem):
                old_path = filesystem.get_path()
                old_path.child('file').setContent(b'content')
                d = pool.change_owner(volume, new_volume)
                d.addCallback(lambda ignored: old_path)
                return d
            d.addCallback(created_filesystem)

            def changed_owner(old_path):
                self.assertFalse(old_path.exists())
            d.addCallback(changed_owner)
            return d

        def test_change_owner_preserves_data(self):
            """
            ``IStoragePool.change_owner()`` moves the data from the filesystem
            for the old volume definition to that for the new volume
            definition.
            """
            pool = fixture(self)
            service = service_for_pool(self, pool)
            volume = service.get(u"volume")
            new_volume = Volume(uuid=u"other-uuid", name=u"volume",
                                service=service)
            d = pool.create(volume)

            def created_filesystem(filesystem):
                path = filesystem.get_path()
                path.child('file').setContent(b'content')

                return pool.change_owner(volume, new_volume)
            d.addCallback(created_filesystem)

            def changed_owner(filesystem):
                path = filesystem.get_path()
                self.assertEqual(path.child('file').getContent(),
                                 b'content')
            d.addCallback(changed_owner)

            return d

        def test_change_owner_existing_target(self):
            """
            ``IStoragePool.change_owner()`` returns a :class:`Deferred` that
            fails with :exception:`FilesystemAlreadyExists`, if the target
            filesystem already exists.
            """
            pool = fixture(self)
            service = service_for_pool(self, pool)
            volume = service.get(u"volume")
            new_volume = Volume(uuid=u"other-uuid", name=u"volume",
                                service=service)
            d = gatherResults([pool.create(volume), pool.create(new_volume)])

            def created_filesystems(igonred):
                return pool.change_owner(volume, new_volume)
            d.addCallback(created_filesystems)

            return self.assertFailure(d, FilesystemAlreadyExists)

        def test_no_snapshots(self):
            """
            If there are no snapshots of a given filesystem,
            ``Filesystem.snapshots`` returns a ``Deferred`` that fires with an
            empty ``list``.
            """
            pool = fixture(self)
            service = service_for_pool(self, pool)
            volume = service.get(u"snapshot-enumeration")
            creating = pool.create(volume)

            def created(filesystem):
                return filesystem.snapshots()

            loading = creating.addCallback(created)
            loading.addCallback(self.assertEqual, [])
            return loading

    return IStoragePoolTests
