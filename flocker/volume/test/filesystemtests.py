# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Generic tests for filesystem APIs.

A "fixture" is a 1-argument callable that takes a :class:`unittest.TestCase`
instance as its first argument and returns some object to be used in a test.
"""

from __future__ import absolute_import

from characteristic import attributes
from zope.interface.verify import verifyObject

from twisted.trial.unittest import TestCase
from twisted.internet.defer import gatherResults
from twisted.application.service import IService

from ...testtools import (
    assertNoFDsLeaked, assert_equal_comparison, assert_not_equal_comparison)

from ..testtools import service_for_pool

from ..filesystems.interfaces import (
    IFilesystemSnapshots, IStoragePool, IFilesystem,
    FilesystemAlreadyExists,
    )
from ..filesystems.errors import MaximumSizeTooSmall
from ..service import Volume, VolumeName
from .._model import VolumeSize


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
            fs_snapshots = fixture(self)
            self.assertTrue(verifyObject(IFilesystemSnapshots, fs_snapshots))

        def test_created(self):
            """
            Snapshots created with ``create()`` are listed in that order in
            ``list()``.
            """
            fs_snapshots = fixture(self)
            d = fs_snapshots.create(b"first")
            d.addCallback(lambda _: fs_snapshots.create(b"another"))
            d.addCallback(lambda _: fs_snapshots.list())
            d.addCallback(self.assertEqual, [b"first", b"another"])
            return d
    return IFilesystemSnapshotsTests


def copy(from_volume, to_volume):
    """Copy contents of one volume to another.

    :param Volume from_volume: Volume to read from.
    :param Volume to_volume: Volume to write to.
    """
    from_filesystem = from_volume.get_filesystem()
    to_filesystem = to_volume.get_filesystem()
    getting_snapshots = to_filesystem.snapshots()

    def got_snapshots(snapshots):
        with from_filesystem.reader(snapshots) as reader:
            with to_filesystem.writer() as writer:
                for chunk in iter(lambda: reader.read(4096), b""):
                    writer.write(chunk)
    getting_snapshots.addCallback(got_snapshots)
    return getting_snapshots


@attributes(["from_volume", "to_volume"])
class CopyVolumes(object):
    """A pair of volumes that had data copied from one to the other.

    :ivar from_volume Volume: Volume data was copied from.
    :ivar to_volume Volume: Volume data was copied to.
    """


# VolumeNames for tests:
MY_VOLUME = VolumeName(namespace=u"myns", dataset_id=u"myvolume")
MY_VOLUME2 = VolumeName(namespace=u"myns", dataset_id=u"myvolume2")


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
    volume = service.get(MY_VOLUME)
    pool2 = fixture(test)
    service2 = service_for_pool(test, pool2)
    volume2 = Volume(
        node_id=service.node_id,
        name=MY_VOLUME,
        service=service2,
    )

    d = pool.create(volume)

    def created_filesystem(filesystem):
        path = filesystem.get_path()
        path.child(b"file").setContent(b"some bytes")
        path.child(b"directory").makedirs()
        copying = copy(volume, volume2)
        copying.addCallback(
            lambda ignored:
            CopyVolumes(from_volume=volume, to_volume=volume2)
        )
        return copying
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


def make_istoragepool_tests(fixture, snapshot_factory):
    """Create a TestCase for IStoragePool.

    :param fixture: A fixture that returns a :class:`IStoragePool`
        provider, and which is assumed to clean up after itself when the
        test is over.
    :param snapshot_factory: A callable that takes a :class:`IFilesystem`
        and returns a corresponding :class:`IFilesystemSnapshots`
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
            volume = service.get(MY_VOLUME)
            d = pool.create(volume)

            def created_filesystem(filesystem):
                self.assertTrue(verifyObject(IFilesystem, filesystem))
            d.addCallback(created_filesystem)
            return d

        def test_create_with_maximum_size(self):
            """
            If a maximum size is specified by the volume, the resulting
            ``IFilesystem`` provider has the same size information.
            """
            pool = fixture(self)
            service = service_for_pool(self, pool)
            volume = service.get(MY_VOLUME)

            size = VolumeSize(maximum_size=1024 * 1024 * 1024)
            volume_with_size = Volume(
                node_id=volume.node_id,
                name=volume.name,
                service=volume.service,
                size=size,
            )

            d = pool.create(volume_with_size)

            def created_filesystem(filesystem):
                self.assertEqual(size, filesystem.size)
            d.addCallback(created_filesystem)
            return d

        def test_resize_volume_new_max_size(self):
            """
            If an existing volume is resized to a new maximum size, the
            resulting ``IFilesystem`` provider has the same new size
            information.
            """
            pool = fixture(self)
            service = service_for_pool(self, pool)
            volume = service.get(MY_VOLUME)

            size = VolumeSize(maximum_size=1024 * 1024 * 1024)
            resized = VolumeSize(maximum_size=1024 * 1024 * 10)
            volume_with_size = Volume(
                node_id=volume.node_id,
                name=volume.name,
                service=volume.service,
                size=size,
            )

            d = pool.create(volume_with_size)

            def created_filesystem(filesystem):
                self.assertEqual(size, filesystem.size)
                volume_with_size.size = resized
                return pool.set_maximum_size(volume_with_size)

            def resized_filesystem(filesystem):
                self.assertEqual(resized, filesystem.size)

            d.addCallback(created_filesystem)
            d.addCallback(resized_filesystem)
            return d

        def test_resize_volume_unlimited_max_size(self):
            """
            If an existing volume is resized to a new maximum size of None, the
            resulting ``IFilesystem`` provider has the same new size
            information.
            """
            pool = fixture(self)
            service = service_for_pool(self, pool)
            volume = service.get(MY_VOLUME)

            size = VolumeSize(maximum_size=1024 * 1024 * 1024)
            resized = VolumeSize(maximum_size=None)
            volume_with_size = Volume(
                node_id=volume.node_id,
                name=volume.name,
                service=volume.service,
                size=size,
            )

            d = pool.create(volume_with_size)

            def created_filesystem(filesystem):
                self.assertEqual(size, filesystem.size)
                volume_with_size.size = resized
                return pool.set_maximum_size(volume_with_size)

            def resized_filesystem(filesystem):
                self.assertEqual(resized, filesystem.size)

            d.addCallback(created_filesystem)
            d.addCallback(resized_filesystem)
            return d

        def test_resize_volume_already_unlimited_size(self):
            """
            If an attempt is made to remove the limit on maximum size of an
            existing volume which already has no maximum size limit, no change
            is made.
            """
            pool = fixture(self)
            service = service_for_pool(self, pool)
            volume = service.get(MY_VOLUME)
            d = pool.create(volume)

            def created_filesystem(filesystem):
                return pool.set_maximum_size(volume)
            d.addCallback(created_filesystem)

            def didnt_resize(filesystem):
                self.assertEqual(
                    VolumeSize(maximum_size=None), filesystem.size)
            d.addCallback(didnt_resize)
            return d

        def test_resize_volume_invalid_max_size(self):
            """
            If an existing volume is resized to a new maximum size which is
            less than the used size of the existing filesystem, a
            ``MaximumSizeTooSmall`` error is raised.
            """
            pool = fixture(self)
            service = service_for_pool(self, pool)
            volume = service.get(MY_VOLUME)

            size = VolumeSize(maximum_size=1024 * 1024 * 1024)
            resized = VolumeSize(maximum_size=1)
            volume_with_size = Volume(
                node_id=volume.node_id,
                name=volume.name,
                service=volume.service,
                size=size,
            )

            d = pool.create(volume_with_size)

            def created_filesystem(filesystem):
                self.assertEqual(size, filesystem.size)
                volume_with_size.size = resized
                return pool.set_maximum_size(volume_with_size)

            def resized_filesystem(filesystem):
                self.assertEqual(resized, filesystem.size)

            def maximum_too_small(reason):
                self.assertTrue(isinstance(reason.value, MaximumSizeTooSmall))

            d.addCallback(created_filesystem)
            d.addErrback(maximum_too_small)
            return d

        def test_two_names_create_different_filesystems(self):
            """
            Two calls to ``create()`` with different volume names return
            different filesystems.
            """
            pool = fixture(self)
            service = service_for_pool(self, pool)
            volume = service.get(MY_VOLUME)
            volume2 = service.get(MY_VOLUME2)
            d = gatherResults([pool.create(volume), pool.create(volume2)])

            def created_filesystems(filesystems):
                first, second = filesystems
                assert_not_equal_comparison(self, first, second)
            d.addCallback(created_filesystems)
            return d

        def test_two_node_id_create_different_filesystems(self):
            """
            Two calls to ``create()`` with different volume manager node IDs
            return different filesystems.
            """
            pool = fixture(self)
            service = service_for_pool(self, pool)
            volume = service.get(MY_VOLUME)
            volume2 = service.get(MY_VOLUME2)
            d = gatherResults([pool.create(volume), pool.create(volume2)])

            def created_filesystems(filesystems):
                first, second = filesystems
                assert_not_equal_comparison(self, first, second)
            d.addCallback(created_filesystems)
            return d

        def test_get_filesystem(self):
            """
            ``get()`` returns the same :class:`IFilesystem` provider as the
            earlier created one.
            """
            pool = fixture(self)
            service = service_for_pool(self, pool)
            volume = service.get(MY_VOLUME)
            d = pool.create(volume)

            def created_filesystem(filesystem):
                filesystem2 = pool.get(volume)
                assert_equal_comparison(self, filesystem, filesystem2)
            d.addCallback(created_filesystem)
            return d

        def test_mountpoint(self):
            """
            The volume's filesystem has a mountpoint which is a directory.
            """
            pool = fixture(self)
            service = service_for_pool(self, pool)
            volume = service.get(MY_VOLUME)
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
            volume = service.get(MY_VOLUME)
            volume2 = service.get(MY_VOLUME2)
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
            volume = service.get(MY_VOLUME)
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
            volume = service.get(MY_VOLUME)
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
                copying = copy(
                    copy_volumes.from_volume, copy_volumes.to_volume)

                def copied(ignored):
                    assertVolumesEqual(
                        self, copy_volumes.from_volume, copy_volumes.to_volume)
                copying.addCallback(copied)
                return copying
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
                copying = copy(volume, volume2)

                def copied(ignored):
                    assertVolumesEqual(self, volume, volume2)
                copying.addCallback(copied)
                return copying
            d.addCallback(got_volumes)
            return d

        def test_exception_passes_through_read(self):
            """
            If an exception is raised in the context of the reader, it is not
            swallowed.
            """
            pool = fixture(self)
            service = service_for_pool(self, pool)
            volume = service.get(MY_VOLUME)
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
            volume = service.get(MY_VOLUME)
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
            volume = service.get(MY_VOLUME)
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
            volume = service.get(MY_VOLUME)
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
                getting_snapshots = to_filesystem.snapshots()

                def got_snapshots(snapshots):
                    try:
                        with from_filesystem.reader(snapshots) as reader:
                            with to_filesystem.writer() as writer:
                                data = reader.read()
                                writer.write(data[:-1])
                                raise ZeroDivisionError()
                    except ZeroDivisionError:
                        pass
                    to_path = volume2.get_filesystem().get_path()
                    self.assertFalse(to_path.child(b"anotherfile").exists())

                getting_snapshots.addCallback(got_snapshots)
                return getting_snapshots

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
            volume = service.get(MY_VOLUME)
            volume2 = service.get(MY_VOLUME2)
            creating = gatherResults([
                pool.create(volume), pool.create(volume2)])

            def created(ignored):
                return pool.enumerate()
            enumerating = creating.addCallback(created)

            def enumerated(result):
                expected = {volume.get_filesystem(), volume2.get_filesystem()}
                self.assertEqual(expected, result)
            return enumerating.addCallback(enumerated)

        def test_enumerate_provides_null_size(self):
            """
            The ``IStoragePool.enumerate`` implementation produces
            ``IFilesystem`` results which specify a ``None`` ``maximum_size``
            when the filesystem was created with no maximum size.
            """
            size = VolumeSize(maximum_size=None)
            pool = fixture(self)
            service = service_for_pool(self, pool)
            volume = service.get(MY_VOLUME, size=size)
            creating = pool.create(volume)

            def created(ignored):
                return pool.enumerate()
            enumerating = creating.addCallback(created)

            def enumerated(result):
                [filesystem] = result
                self.assertEqual(size, filesystem.size)
            enumerating.addCallback(enumerated)
            return enumerating

        def test_enumerate_provides_size(self):
            """
            The ``IStoragePool.enumerate`` implementation produces
            ``IFilesystem`` results which reflect the size configuration
            those filesystems were created with.
            """
            size = VolumeSize(maximum_size=54321)
            pool = fixture(self)
            service = service_for_pool(self, pool)
            volume = service.get(MY_VOLUME, size=size)
            creating = pool.create(volume)

            def created(ignored):
                return pool.enumerate()
            enumerating = creating.addCallback(created)

            def enumerated(result):
                [filesystem] = result
                self.assertEqual(size, filesystem.size)
            enumerating.addCallback(enumerated)
            return enumerating

        def test_enumerate_spaces(self):
            """
            The ``IStoragePool.enumerate`` implementation doesn't return
            a ``Deferred`` that fires with a ``Failure`` if there is a
            filesystem with a space in it.
            """
            pool = fixture(self)
            service = service_for_pool(self, pool)
            volume = service.get(
                VolumeName(namespace=u"ns", dataset_id=u"spaced name"))
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
                https://clusterhq.atlassian.net/browse/FLOC-78
            """
            pool = fixture(self)
            volume_name = MY_VOLUME
            service = service_for_pool(self, pool)
            node_id = service.node_id
            volume = service.get(volume_name)
            d = pool.create(volume)

            def createdFilesystem(filesystem):
                name = filesystem.get_path().basename()
                expected = u"{node_id}.{name}".format(
                    node_id=node_id, name=volume_name.to_bytes())
                self.assertEqual(name, expected)
            d.addCallback(createdFilesystem)
            return d

        def test_change_owner_creates_new(self):
            """
            ``IFilesystem.change_owner()`` creates a filesystem for the new
            volume definition.
            """
            pool = fixture(self)
            service = service_for_pool(self, pool)
            volume = service.get(MY_VOLUME)
            new_volume = Volume(node_id=u"new-uuid", name=MY_VOLUME2,
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
            volume = service.get(MY_VOLUME)
            new_volume = Volume(node_id=u"new-uuid", name=MY_VOLUME2,
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
            volume = service.get(MY_VOLUME)
            new_volume = Volume(node_id=u"other-uuid", name=MY_VOLUME2,
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
            volume = service.get(MY_VOLUME)
            new_volume = Volume(node_id=u"other-uuid", name=MY_VOLUME2,
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
            volume = service.get(MY_VOLUME)
            creating = pool.create(volume)

            def created(filesystem):
                loading = filesystem.snapshots()
                loading.addCallback(self.assertEqual, [])
                return loading

            creating.addCallback(created)
            return creating

        def test_clone_to_creates_new(self):
            """
            ``IFilesystem.clone_to()`` creates a filesystem for the new
            volume definition.
            """
            pool = fixture(self)
            service = service_for_pool(self, pool)
            volume = service.get(MY_VOLUME)
            new_volume = Volume(node_id=u"new-uuid", name=MY_VOLUME2,
                                service=service)
            d = pool.create(volume)
            d.addCallback(lambda _: pool.clone_to(volume, new_volume))

            def cloned(new_filesystem):
                old_path = volume.get_filesystem().get_path()
                new_path = new_filesystem.get_path()
                self.assertNotEqual(old_path, new_path)
            d.addCallback(cloned)
            return d

        def test_clone_to_copies_data(self):
            """
            ``IStoragePool.clone_to()`` copies the data from the filesystem for
            the old volume definition to that for the new volume
            definition.
            """
            pool = fixture(self)
            service = service_for_pool(self, pool)
            volume = service.get(MY_VOLUME)
            new_volume = Volume(node_id=u"other-uuid", name=MY_VOLUME2,
                                service=service)
            d = pool.create(volume)

            def created_filesystem(filesystem):
                path = filesystem.get_path()
                path.child('file').setContent(b'content')

                return pool.clone_to(volume, new_volume)
            d.addCallback(created_filesystem)

            def cloned(filesystem):
                path = filesystem.get_path()
                self.assertEqual(path.child('file').getContent(),
                                 b'content')
            d.addCallback(cloned)

            return d

        def test_clone_to_old_distinct_filesystems(self):
            """
            The filesystem created by ``IStoragePool.clone_to()`` and the
            original filesystem are independent; writes to one do not affect
            the other.
            """
            pool = fixture(self)
            service = service_for_pool(self, pool)
            volume = service.get(MY_VOLUME)
            new_volume = service.get(MY_VOLUME2)
            d = pool.create(volume)

            def created_filesystem(filesystem):
                return pool.clone_to(volume, new_volume)
            d.addCallback(created_filesystem)

            def cloned(_):
                old_path = volume.get_filesystem().get_path()
                old_path.child('old').setContent(b'old')
                new_path = new_volume.get_filesystem().get_path()
                new_path.child(b'new').setContent(b'new')
                self.assertEqual([False, False],
                                 [old_path.child(b'new').exists(),
                                  new_path.child(b'old').exists()])
            d.addCallback(cloned)
            return d

        def test_clone_to_existing_target(self):
            """
            ``IStoragePool.clone_to()`` returns a :class:`Deferred` that
            fails with :exception:`FilesystemAlreadyExists`, if the target
            filesystem already exists.
            """
            pool = fixture(self)
            service = service_for_pool(self, pool)
            volume = service.get(MY_VOLUME)
            new_volume = Volume(node_id=u"other-uuid", name=MY_VOLUME2,
                                service=service)
            d = gatherResults([pool.create(volume), pool.create(new_volume)])

            def created_filesystems(ignored):
                return pool.clone_to(volume, new_volume)
            d.addCallback(created_filesystems)

            return self.assertFailure(d, FilesystemAlreadyExists)

        def test_destroy(self):
            """
            A filesystem destroyed by ``IStoragePool.destroy`` doesn't show up
            in ``IStoragePool.enumerate``.
            """
            pool = fixture(self)
            service = service_for_pool(self, pool)
            volume = service.get(MY_VOLUME)
            d = pool.create(volume)
            d.addCallback(lambda _: pool.destroy(volume))
            d.addCallback(lambda _: pool.enumerate())
            d.addCallback(lambda result: self.assertEqual(list(result), []))
            return d

        def test_destroy_after_snapshot(self):
            """
            A filesystem with snapshots that is destroyed by
            ``IStoragePool.destroy`` doesn't show up in
            ``IStoragePool.enumerate``.
            """
            pool = fixture(self)
            service = service_for_pool(self, pool)
            volume = service.get(MY_VOLUME)
            d = pool.create(volume)
            d.addCallback(lambda fs: snapshot_factory(fs).create(b"cheese"))
            d.addCallback(lambda _: pool.destroy(volume))
            d.addCallback(lambda _: pool.enumerate())
            d.addCallback(lambda result: self.assertEqual(list(result), []))
            return d

    return IStoragePoolTests
