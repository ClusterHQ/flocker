# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""Tests for :module:`flocker.volume.service`."""

from __future__ import absolute_import

from io import BytesIO
import sys
import json
from contextlib import contextmanager

from uuid import uuid4
from StringIO import StringIO

from zope.interface import implementer
from zope.interface.verify import verifyObject

from twisted.application.service import IService, Service
from twisted.internet.task import Clock
from twisted.python.filepath import FilePath, Permissions
from twisted.trial.unittest import SynchronousTestCase, TestCase

from ..service import (
    VolumeService, CreateConfigurationError, Volume, VolumeName,
    VolumeScript, ICommandLineVolumeScript,
    VolumeSize,
    )
from ..script import VolumeOptions

from ..filesystems.memory import FilesystemStoragePool
from ..filesystems.zfs import StoragePool
from .._ipc import RemoteVolumeManager, LocalVolumeManager
from ..testtools import create_volume_service
from ...common import FakeNode
from ...testtools import (
    skip_on_broken_permissions, attempt_effective_uid, make_with_init_tests,
    assert_equal_comparison, assert_not_equal_comparison,
    )


class VolumeNameInitializationTests(make_with_init_tests(
        VolumeName, {"namespace": u"x", "dataset_id": u"y"})):
    """
    Tests for :class:`VolumeName` initialization.
    """


class VolumeNameTests(TestCase):
    """
    Tests for :class:`VolumeName`.
    """
    def test_equality(self):
        """
        ``VolumeName`` with same arguments are equal.
        """
        name1 = VolumeName(namespace=u"blah", dataset_id="bloo")
        name2 = VolumeName(namespace=u"blah", dataset_id="bloo")
        self.assertEqual([name1 == name2, name1 != name2],
                         [True, False])

    def test_inequality(self):
        """
        ``VolumeName`` with different arguments are unequal.
        """
        name1 = VolumeName(namespace=u"blah", dataset_id="bloo")
        name2 = VolumeName(namespace=u"blah", dataset_id="bloo2")
        name3 = VolumeName(namespace=u"blah2", dataset_id="bloo")
        self.assertEqual([name1 == name2, name1 == name3, name1 != name2,
                          name1 != name3], [False, False, True, True])

    def test_to_bytes(self):
        """
        ``VolumeName.to_bytes`` converts the volume name to bytes.
        """
        name = VolumeName(namespace=u"blah", dataset_id="bloo")
        self.assertEqual(name.to_bytes(), b"blah.bloo")

    def test_from_bytes(self):
        """
        ``VolumeName.from_bytes`` converts bytes back into a ``VolumeName``.
        """
        self.assertEqual(VolumeName.from_bytes(b"lah.loo"),
                         VolumeName(namespace=u"lah", dataset_id="loo"))

    def test_no_period_in_namespace(self):
        """
        ``VolumeName`` namespaces can't have a period.
        """
        self.assertRaises(ValueError, VolumeName, namespace=u".x",
                          dataset_id=u"y")


class VolumeSizeInitializationTests(make_with_init_tests(
        VolumeSize, {"maximum_size": 12345678})):
    """
    Tests for :class:`VolumeSize` initialization.
    """


class VolumeSizeTests(TestCase):
    """
    Tests for :class:`VolumeSize`.
    """
    def test_immutable(self):
        """
        Attributes of :class:`VolumeSize` instances cannot be set.
        """
        size = VolumeSize(maximum_size=12345)
        self.assertRaises(AttributeError, setattr, size, "maximum_size", 123)


class VolumeSizeComparisonTests(TestCase):
    """
    Tests for :class:`VolumeSize` equality.
    """
    def test_self(self):
        """
        A :class:`VolumeSize` instance compares as equal to itself.
        """
        size = VolumeSize(maximum_size=12345)
        assert_equal_comparison(self, size, size)

    def test_equal(self):
        """
        Two :class:`VolumeSize` instances with the same value for the
        ``maximum_size`` attribute compare equal to each other.
        """
        a = VolumeSize(maximum_size=12345)
        b = VolumeSize(maximum_size=12345)
        assert_equal_comparison(self, a, b)

    def test_maximum_size_differs(self):
        """
        Two :class:`VolumeSize` instances with different values for the
        ``maximum_size`` attribute do not compare equal to each other.
        """
        a = VolumeSize(maximum_size=12345)
        b = VolumeSize(maximum_size=54321)
        assert_not_equal_comparison(self, a, b)


class VolumeServiceStartupTests(TestCase):
    """
    Tests for :class:`VolumeService` startup.
    """
    def test_interface(self):
        """:class:`VolumeService` implements :class:`IService`."""
        self.assertTrue(verifyObject(IService,
                                     VolumeService(FilePath(""), None,
                                                   reactor=Clock())))

    def test_no_config_UUID(self):
        """If no config file exists in the given path, a new UUID is chosen."""
        service = create_volume_service(self)
        service2 = create_volume_service(self)
        self.assertNotEqual(service.node_id, service2.node_id)

    def test_no_config_written(self):
        """If no config file exists, a new one is written with the UUID."""
        path = FilePath(self.mktemp())
        service = VolumeService(path,
                                FilesystemStoragePool(FilePath(self.mktemp())),
                                reactor=Clock())
        service.startService()
        config = json.loads(path.getContent())
        self.assertEqual({u"uuid": service.node_id, u"version": 1}, config)

    def test_no_config_directory(self):
        """The config file's parent directory is created if it
        doesn't exist."""
        path = FilePath(self.mktemp()).child(b"config.json")
        service = VolumeService(path,
                                FilesystemStoragePool(FilePath(self.mktemp())),
                                reactor=Clock())
        service.startService()
        self.assertTrue(path.exists())

    @skip_on_broken_permissions
    def test_config_makedirs_failed(self):
        """If creating the config directory fails then CreateConfigurationError
        is raised."""
        path = FilePath(self.mktemp())
        path.makedirs()
        path.chmod(0)
        self.addCleanup(path.chmod, 0o777)
        path = path.child(b"dir").child(b"config.json")
        service = VolumeService(path,
                                FilesystemStoragePool(FilePath(self.mktemp())),
                                reactor=Clock())
        with attempt_effective_uid('nobody', suppress_errors=True):
            self.assertRaises(CreateConfigurationError, service.startService)

    @skip_on_broken_permissions
    def test_config_write_failed(self):
        """If writing the config fails then CreateConfigurationError
        is raised."""
        path = FilePath(self.mktemp())
        path.makedirs()
        path.chmod(0)
        self.addCleanup(path.chmod, 0o777)
        path = path.child(b"config.json")
        service = VolumeService(path,
                                FilesystemStoragePool(FilePath(self.mktemp())),
                                reactor=Clock())
        with attempt_effective_uid('nobody', suppress_errors=True):
            self.assertRaises(CreateConfigurationError, service.startService)

    def test_config(self):
        """If a config file exists, the UUID is loaded from it."""
        path = self.mktemp()
        service = VolumeService(FilePath(path),
                                FilesystemStoragePool(FilePath(self.mktemp())),
                                reactor=Clock())
        service.startService()
        service2 = VolumeService(
            FilePath(path),
            FilesystemStoragePool(FilePath(self.mktemp())),
            reactor=Clock())
        service2.startService()
        self.assertEqual(service.node_id, service2.node_id)

    def test_start_pool(self):
        """
        The storage pool service is started by ``VolumeService.startService``.
        """
        pool = FilesystemStoragePool(FilePath(self.mktemp()))
        service = VolumeService(FilePath(self.mktemp()), pool, Clock())
        running_before_start = pool.running
        service.startService()
        self.assertEqual((running_before_start, pool.running), (False, True))


# VolumeName for tests:
MY_VOLUME = VolumeName(namespace=u"myns", dataset_id=u"myvolume")
MY_VOLUME2 = VolumeName(namespace=u"myns", dataset_id=u"myvolume2")


class VolumeServiceAPITests(TestCase):
    """Tests for the ``VolumeService`` API."""

    def test_set_maximum_size(self):
        """
        ``set_maximum_size`` returns a ``Deferred` that fires with a
        ``Volume`` that has the new size set on it.
        """
        pool = FilesystemStoragePool(FilePath(self.mktemp()))
        service = VolumeService(FilePath(self.mktemp()), pool, reactor=Clock())
        service.startService()
        d = service.create(service.get(MY_VOLUME))
        volume_size = VolumeSize(maximum_size=1024 * 1024 * 10)
        resized_volume = Volume(node_id=service.node_id, name=MY_VOLUME,
                                service=service, size=volume_size)
        d = service.set_maximum_size(service.get(MY_VOLUME, size=volume_size))
        self.assertEqual(self.successResultOf(d), resized_volume)

    def test_set_maximum_size_applied(self):
        """
        ``set_maximum_size`` results in the associated filesystem having a
        new maximum size quota applied according to the given ``Volume``.
        """
        pool = FilesystemStoragePool(FilePath(self.mktemp()))
        service = VolumeService(FilePath(self.mktemp()), pool, reactor=Clock())
        service.startService()
        d = service.create(service.get(MY_VOLUME))
        created_volume = self.successResultOf(d)
        created_fs = pool.get(created_volume)
        volume_size = VolumeSize(maximum_size=1024 * 1024 * 10)
        d = service.set_maximum_size(service.get(MY_VOLUME, size=volume_size))
        resized_volume = self.successResultOf(d)
        resized_fs = pool.get(resized_volume)
        self.assertEqual(created_fs.size, VolumeSize(maximum_size=None))
        self.assertEqual(resized_volume.size, resized_fs.size)

    def test_create_result(self):
        """``create()`` returns a ``Deferred`` that fires with a ``Volume``."""
        pool = FilesystemStoragePool(FilePath(self.mktemp()))
        service = VolumeService(FilePath(self.mktemp()), pool, reactor=Clock())
        service.startService()
        d = service.create(service.get(MY_VOLUME))
        self.assertEqual(
            self.successResultOf(d),
            Volume(node_id=service.node_id, name=MY_VOLUME, service=service))

    def _creation_test(self, get_volume):
        """
        Assert that the creation of a volume using ``VolumeService.create``
        results in the associated filesystem also being created and the size
        parameters being set according to the given ``Volume`` instance.

        :param get_volume: A function which accepts a started ``VolumeService``
            instance and returns a ``Volume`` instance to create.
        """
        pool = FilesystemStoragePool(FilePath(self.mktemp()))
        service = VolumeService(FilePath(self.mktemp()), pool, reactor=Clock())
        service.startService()
        volume = get_volume(service)
        created_volume = self.successResultOf(service.create(volume))
        created_fs = pool.get(volume)
        fs_path = created_fs.get_path()
        self.assertEqual(
            (True, volume.size, volume.size),
            (fs_path.isdir(), created_volume.size, created_fs.size)
        )

    def test_create_filesystem_with_size(self):
        """
        ``create()`` creates the volume's filesystem respecting the specified
        ``VolumeSize`` maximum_size.
        """
        size = VolumeSize(maximum_size=100000000)
        self._creation_test(lambda service: service.get(MY_VOLUME, size=size))

    def test_create_filesystem(self):
        """
        ``create()`` creates the volume's filesystem.
        """
        size = VolumeSize(maximum_size=None)
        self._creation_test(lambda service: service.get(MY_VOLUME, size=size))

    @skip_on_broken_permissions
    def test_create_mode(self):
        """The created filesystem is readable/writable/executable by anyone.

        A better alternative will be implemented in
        https://clusterhq.atlassian.net/browse/FLOC-34
        """
        pool = FilesystemStoragePool(FilePath(self.mktemp()))
        service = VolumeService(FilePath(self.mktemp()), pool, reactor=Clock())
        service.startService()
        volume = self.successResultOf(service.create(service.get(MY_VOLUME)))
        self.assertEqual(pool.get(volume).get_path().getPermissions(),
                         Permissions(0o777))

    def test_clone_to_result(self):
        """
        ``clone_to()`` returns a ``Deferred`` that fires with a ``Volume``.
        """
        pool = FilesystemStoragePool(FilePath(self.mktemp()))
        service = VolumeService(FilePath(self.mktemp()), pool, reactor=Clock())
        service.startService()
        parent = self.successResultOf(service.create(service.get(MY_VOLUME)))
        d = service.clone_to(parent, MY_VOLUME2)

        self.assertEqual(
            self.successResultOf(d),
            Volume(node_id=service.node_id, name=MY_VOLUME2, service=service))

    def test_clone_to_creates_copied_filesystem(self):
        """
        ``clone_to()`` creates the volume's filesystem from the parent's
        filesystem.
        """
        pool = FilesystemStoragePool(FilePath(self.mktemp()))
        service = VolumeService(FilePath(self.mktemp()), pool, reactor=Clock())
        service.startService()
        parent = self.successResultOf(service.create(service.get(MY_VOLUME)))
        parent_file = parent.get_filesystem().get_path().child(b"file")
        parent_file.setContent(b"blah")

        volume = self.successResultOf(service.clone_to(parent, MY_VOLUME2))
        self.assertEqual(
            pool.get(volume).get_path().child(b"file").getContent(),
            b"blah")

    def test_clone_to_new_filesystem(self):
        """
        ``clone_to()`` creates a new filesystem.
        """
        pool = FilesystemStoragePool(FilePath(self.mktemp()))
        service = VolumeService(FilePath(self.mktemp()), pool, reactor=Clock())
        service.startService()
        parent = self.successResultOf(service.create(service.get(MY_VOLUME)))
        parent_file = parent.get_filesystem().get_path().child(b"file")
        parent_file.setContent(b"blah")

        volume = self.successResultOf(service.clone_to(parent, MY_VOLUME2))
        pool.get(volume).get_path().child(b"file").setContent(b"changed")
        self.assertEqual(parent_file.getContent(), b"blah")

    @skip_on_broken_permissions
    def test_clone_to_mode(self):
        """
        The cloned-to filesystem is readable/writable/executable by anyone.

        A better alternative will be implemented in
        https://clusterhq.atlassian.net/browse/FLOC-34
        """
        pool = FilesystemStoragePool(FilePath(self.mktemp()))
        service = VolumeService(FilePath(self.mktemp()), pool, reactor=Clock())
        service.startService()
        parent = self.successResultOf(service.create(service.get(MY_VOLUME)))

        volume = self.successResultOf(service.clone_to(parent, MY_VOLUME2))
        self.assertEqual(pool.get(volume).get_path().getPermissions(),
                         Permissions(0o777))

    def test_get(self):
        """
        ``VolumeService.get`` creates a ``Volume`` instance owned by that
        service and with given name.
        """
        service = create_volume_service(self)
        self.assertEqual(service.get(MY_VOLUME),
                         Volume(node_id=service.node_id, name=MY_VOLUME,
                                service=service))

    def test_get_extra_args(self):
        """
        Additional keyword arguments passed to ``VolumeService.get`` are passed
        on to the ``Volume`` initializer.
        """
        service = create_volume_service(self)
        size = VolumeSize(maximum_size=54321)
        self.assertEqual(size, service.get(MY_VOLUME, size=size).size)

    def test_push_different_node_id(self):
        """Pushing a remotely-owned volume results in a ``ValueError``."""
        pool = FilesystemStoragePool(FilePath(self.mktemp()))
        service = VolumeService(FilePath(self.mktemp()), pool, reactor=Clock())
        service.startService()

        volume = Volume(node_id=u"wronguuid", name=MY_VOLUME, service=service)
        self.assertRaises(ValueError, service.push, volume,
                          RemoteVolumeManager(FakeNode()))

    def test_push_writes_filesystem(self):
        """
        Pushing a locally-owned volume writes its filesystem to the remote
        process.
        """
        pool = FilesystemStoragePool(FilePath(self.mktemp()))
        service = VolumeService(FilePath(self.mktemp()), pool, reactor=Clock())
        service.startService()
        volume = self.successResultOf(service.create(service.get(MY_VOLUME)))
        filesystem = volume.get_filesystem()
        filesystem.get_path().child(b"foo").setContent(b"blah")
        with filesystem.reader() as reader:
            data = reader.read()
        node = FakeNode([
            # Hard-code the knowledge that first `flocker-volume snapshots` is
            # run.  It doesn't need to produce any particular output for this
            # test, it just needs to not fail.
            b"",
        ])

        self.successResultOf(service.push(volume, RemoteVolumeManager(node)))

        self.assertEqual(node.stdin.read(), data)

    def test_push_with_snapshots(self):
        """
        Pushing a locally-owned volume to a remote volume manager which has a
        snapshot in common with the local volume manager results in an
        incremental data stream.
        """

        class FakeVolumeManager(object):
            def __init__(self):
                self.written = []

            def snapshots(self, volume):
                return volume.get_filesystem().snapshots()

            @contextmanager
            def receive(self, volume):
                writer = BytesIO()
                yield writer
                self.written.append(writer)

        pool = FilesystemStoragePool(FilePath(self.mktemp()))
        service = VolumeService(FilePath(self.mktemp()), pool, reactor=Clock())
        service.startService()
        volume = self.successResultOf(service.create(service.get(MY_VOLUME)))
        filesystem = volume.get_filesystem()
        filesystem.snapshot(b"stuff")

        remote_manager = FakeVolumeManager()

        self.successResultOf(service.push(volume, remote_manager))

        writer = remote_manager.written.pop()
        self.assertEqual(
            [b"incremental stream based on", b"stuff"],
            writer.getvalue().splitlines()[-2:])

    def test_receive_local_node_id(self):
        """
        If a volume with the same node ID as the service is received,
        ``ValueError`` is raised.
        """
        pool = FilesystemStoragePool(FilePath(self.mktemp()))
        service = VolumeService(FilePath(self.mktemp()), pool, reactor=Clock())
        service.startService()

        self.assertRaises(ValueError, service.receive,
                          service.node_id.encode("ascii"), b"lalala", None)

    def test_receive_creates_volume(self):
        """Receiving creates a volume with the given node_id and name."""
        pool = FilesystemStoragePool(FilePath(self.mktemp()))
        service = VolumeService(FilePath(self.mktemp()), pool, reactor=Clock())
        service.startService()
        volume = self.successResultOf(service.create(service.get(MY_VOLUME)))
        filesystem = volume.get_filesystem()

        manager_node_id = unicode(uuid4())
        new_name = VolumeName(namespace=u"myns", dataset_id=u"newvolume")

        with filesystem.reader() as reader:
            service.receive(manager_node_id, new_name, reader)
        new_volume = Volume(node_id=manager_node_id, name=new_name,
                            service=service)
        d = service.enumerate()

        def got_volumes(volumes):
            # Consume the generator into a list.  Using `assertIn` on a
            # generator produces bad failure messages.
            volumes = list(volumes)
            self.assertIn(new_volume, volumes)
        d.addCallback(got_volumes)
        return d

    def test_receive_creates_files(self):
        """Receiving creates filesystem with the given push data."""
        pool = FilesystemStoragePool(FilePath(self.mktemp()))
        service = VolumeService(FilePath(self.mktemp()), pool, reactor=Clock())
        service.startService()
        volume = self.successResultOf(service.create(service.get(MY_VOLUME)))
        filesystem = volume.get_filesystem()
        filesystem.get_path().child(b"afile").setContent(b"lalala")

        manager_node_id = unicode(uuid4())
        new_name = VolumeName(namespace=u"myns", dataset_id=u"newvolume")

        with filesystem.reader() as reader:
            service.receive(manager_node_id, new_name, reader)

        new_volume = Volume(node_id=manager_node_id, name=new_name,
                            service=service)
        root = new_volume.get_filesystem().get_path()
        self.assertTrue(root.child(b"afile").getContent(), b"lalala")

    def test_enumerate_no_volumes(self):
        """``enumerate()`` returns no volumes when there are no volumes."""
        pool = FilesystemStoragePool(FilePath(self.mktemp()))
        service = VolumeService(FilePath(self.mktemp()), pool, reactor=Clock())
        service.startService()
        volumes = self.successResultOf(service.enumerate())
        self.assertEqual([], list(volumes))

    def test_enumerate_with_size(self):
        """
        ``enumerate()`` includes a ``VolumeSize`` object in the size attribute
        of volumes previously ``create()``ed.
        """
        pool = FilesystemStoragePool(FilePath(self.mktemp()))
        service = VolumeService(FilePath(self.mktemp()), pool, reactor=Clock())
        service.startService()
        names = set(VolumeName(namespace=u"ns", dataset_id=i)
                    for i in (u"somevolume", u"anotherone", u"lastone"))
        expected = {
            self.successResultOf(service.create(service.get(name)))
            for name in names}
        actual = self.successResultOf(service.enumerate())
        self.assertEqual(
            set(
                (volume.node_id, volume.size, volume.name)
                for volume in expected
            ),
            set(
                (volume.node_id, volume.size, volume.name) for volume in actual
            ))

    def test_enumerate_some_volumes(self):
        """``enumerate()`` returns all volumes previously ``create()``ed."""
        pool = FilesystemStoragePool(FilePath(self.mktemp()))
        service = VolumeService(FilePath(self.mktemp()), pool, reactor=Clock())
        service.startService()
        names = set(VolumeName(namespace=u"ns", dataset_id=i)
                    for i in (u"somevolume", u"anotherone", u"lastone"))
        expected = {
            self.successResultOf(service.create(service.get(name)))
            for name in names}
        service2 = VolumeService(FilePath(self.mktemp()), pool,
                                 reactor=Clock())
        service2.startService()
        actual = self.successResultOf(service2.enumerate())
        self.assertEqual(
            set((volume.node_id, volume.name) for volume in expected),
            set((volume.node_id, volume.name) for volume in actual))

    def test_enumerate_a_volume_with_period(self):
        """``enumerate()`` returns a volume previously ``create()``ed when its
        name includes a period."""
        pool = FilesystemStoragePool(FilePath(self.mktemp()))
        service = VolumeService(FilePath(self.mktemp()), pool, reactor=Clock())
        service.startService()
        expected = self.successResultOf(service.create(
            service.get(VolumeName(namespace=u"ns",
                                   dataset_id=u"some.volume"))))
        actual = self.successResultOf(service.enumerate())
        self.assertEqual([expected], list(actual))

    def test_enumerate_skips_other_filesystems(self):
        """
        The result of ``enumerate()`` does not include any volumes representing
        filesystems named outside of the Flocker naming convention (which may
        have been created directly by the user).
        """
        path = FilePath(self.mktemp())
        path.child(b"arbitrary stuff").makedirs()
        path.child(b"stuff\tarbitrary").makedirs()
        path.child(b"non-uuid.stuff").makedirs()

        pool = FilesystemStoragePool(path)
        service = VolumeService(FilePath(self.mktemp()), pool, reactor=Clock())
        service.startService()

        name = VolumeName(namespace=u"mynspaces",
                          dataset_id=u"good_volume_name")
        self.successResultOf(service.create(service.get(name)))

        volumes = list(self.successResultOf(service.enumerate()))
        self.assertEqual(
            [Volume(node_id=service.node_id, name=name, service=service)],
            volumes)

    def test_acquire_rejects_local_volume(self):
        """
        ``VolumeService.acquire()`` errbacks with a ``ValueError`` if given a
        locally-owned volume.
        """
        service = VolumeService(FilePath(self.mktemp()),
                                FilesystemStoragePool(FilePath(self.mktemp())),
                                reactor=Clock())
        service.startService()
        self.addCleanup(service.stopService)

        self.failureResultOf(service.acquire(service.node_id, u"blah"),
                             ValueError)

    # Further tests for acquire() are done in
    # test_ipc.make_iremote_volume_manager.

    def test_handoff_rejects_remote_volume(self):
        """
        ``VolumeService.handoff()`` errbacks with a ``ValueError`` if given a
        remotely-owned volume.
        """
        service = create_volume_service(self)
        remote_volume = Volume(node_id=u"remote", name=MY_VOLUME,
                               service=service)

        self.failureResultOf(service.handoff(remote_volume, None),
                             ValueError)

    def test_handoff_destination_acquires(self):
        """
        ``VolumeService.handoff()`` makes the remote node owner of the volume
        previously owned by the original owner.
        """
        origin_service = create_volume_service(self)
        destination_service = create_volume_service(self)

        created = origin_service.create(origin_service.get(MY_VOLUME))

        def got_volume(volume):
            volume.get_filesystem().get_path().child(b"afile").setContent(
                b"exists")
            return origin_service.handoff(
                volume, LocalVolumeManager(destination_service))
        created.addCallback(got_volume)

        def handed_off(_):
            expected_volume = Volume(node_id=destination_service.node_id,
                                     name=MY_VOLUME,
                                     service=destination_service)
            root = expected_volume.get_filesystem().get_path()
            self.assertEqual(root.child(b"afile").getContent(), b"exists")
        created.addCallback(handed_off)
        return created

    def test_handoff_changes_node_id(self):
        """
        ```VolumeService.handoff()`` changes the owner node ID of the local
        volume to the new owner's node ID.
        """
        origin_service = create_volume_service(self)
        destination_service = create_volume_service(self)

        created = origin_service.create(origin_service.get(MY_VOLUME))

        def got_volume(volume):
            return origin_service.handoff(
                volume, LocalVolumeManager(destination_service))
        created.addCallback(got_volume)
        created.addCallback(lambda _: origin_service.enumerate())

        def got_origin_volumes(volumes):
            expected_volume = Volume(node_id=destination_service.node_id,
                                     name=MY_VOLUME,
                                     service=origin_service)
            self.assertEqual(list(volumes), [expected_volume])
        created.addCallback(got_origin_volumes)
        return created

    def test_handoff_preserves_data(self):
        """
        ``VolumeService.handoff()`` preserves the data from the relinquished
        volume in the newly owned resulting volume in the local volume manager.
        """
        origin_service = create_volume_service(self)
        destination_service = create_volume_service(self)

        created = origin_service.create(origin_service.get(MY_VOLUME))

        def got_volume(volume):
            volume.get_filesystem().get_path().child(b"afile").setContent(
                b"exists")
            return origin_service.handoff(
                volume, LocalVolumeManager(destination_service))
        created.addCallback(got_volume)

        def handed_off(volumes):
            expected_volume = Volume(node_id=destination_service.node_id,
                                     name=MY_VOLUME,
                                     service=origin_service)
            root = expected_volume.get_filesystem().get_path()
            self.assertEqual(root.child(b"afile").getContent(), b"exists")
        created.addCallback(handed_off)
        return created


class VolumeInitializationTests(make_with_init_tests(
        Volume,
        kwargs={
            "node_id": u"abcd",
            "name": VolumeName(namespace=u"xyz", dataset_id=u"123"),
            "service": object(),
            "size": VolumeSize(maximum_size=54321),
        },
        expected_defaults={
            "size": VolumeSize(maximum_size=None),
        })):
    """
    Tests for :class:`Volume` initialization.
    """


class VolumeTests(TestCase):
    """
    Tests for ``Volume``.
    """

    def setUp(self):
        self.size = VolumeSize(maximum_size=12345)

    def test_equality(self):
        """
        Volumes are equal if they have the same name, node_id and pool.
        """
        service = object()
        v1 = Volume(
            node_id=u"123", name=MY_VOLUME, service=service, size=self.size)
        v2 = Volume(
            node_id=u"123", name=MY_VOLUME, service=service, size=self.size)
        assert_equal_comparison(self, v1, v2)

    def test_inequality_node_id(self):
        """
        Volumes are unequal if they have different node_ids.
        """
        service = object()
        v1 = Volume(
            node_id=u"123", name=MY_VOLUME, service=service, size=self.size)
        v2 = Volume(
            node_id=u"123zz", name=MY_VOLUME, service=service, size=self.size)
        assert_not_equal_comparison(self, v1, v2)

    def test_inequality_name(self):
        """
        Volumes are unequal if they have different names.
        """
        service = object()
        v1 = Volume(
            node_id=u"123", name=MY_VOLUME, service=service, size=self.size)
        v2 = Volume(
            node_id=u"123", name=VolumeName(namespace=u"mys",
                                            dataset_id=u"456zz"),
            service=service, size=self.size,
        )
        assert_not_equal_comparison(self, v1, v2)

    def test_inequality_service(self):
        """
        Volumes are unequal if they have different services.
        """
        v1 = Volume(
            node_id=u"123", name=MY_VOLUME, service=object(), size=self.size)
        v2 = Volume(
            node_id=u"123", name=MY_VOLUME, service=object(), size=self.size)
        assert_not_equal_comparison(self, v1, v2)

    def test_inequality_size(self):
        """
        Volumes are unequal if they have different sizes.
        """
        service = object()
        v1 = Volume(
            node_id=u"123", name=MY_VOLUME, service=service,
            size=VolumeSize(maximum_size=12345),
        )
        v2 = Volume(
            node_id=u"123", name=MY_VOLUME, service=service,
            size=VolumeSize(maximum_size=54321),
        )
        assert_not_equal_comparison(self, v1, v2)

    def test_get_filesystem(self):
        """``Volume.get_filesystem`` returns the filesystem for the volume."""
        pool = FilesystemStoragePool(FilePath(self.mktemp()))
        service = VolumeService(FilePath(self.mktemp()), pool, None)
        volume = Volume(node_id=u"123", name=MY_VOLUME, service=service)
        self.assertEqual(volume.get_filesystem(), pool.get(volume))

    def test_is_locally_owned(self):
        """
        ``Volume.locally_owned()`` indicates whether the volume's owner node ID
        matches that of the local volume manager.
        """
        service = create_volume_service(self)
        local = service.get(MY_VOLUME)
        remote = Volume(node_id=service.node_id + u"extra", name=MY_VOLUME2,
                        service=service)
        self.assertEqual((local.locally_owned(), remote.locally_owned()),
                         (True, False))


class VolumeOwnerChangeTests(TestCase):
    """
    Tests for ``Volume.change_owner``.
    """
    def setUp(self):
        """
        Create a ``VolumeService`` pointing at a new pool.
        """
        pool = FilesystemStoragePool(FilePath(self.mktemp()))
        self.service = VolumeService(FilePath(self.mktemp()), pool,
                                     reactor=Clock())
        self.service.startService()
        self.other_node_id = unicode(uuid4())

    def test_return(self):
        """
        ``Volume.change_owner`` returns a ``Deferred`` that fires with a new
        ``Volume`` with the new owner node ID and the same name.
        """
        volume = self.successResultOf(
            self.service.create(self.service.get(MY_VOLUME))
        )
        new_volume = self.successResultOf(
            volume.change_owner(self.other_node_id))
        self.assertEqual(
            {'node_id': new_volume.node_id, 'name': new_volume.name},
            {'node_id': self.other_node_id, 'name': MY_VOLUME})

    def test_filesystem(self):
        """
        The filesystem for the new ``Volume`` preserves data from the old one.
        """
        volume = self.successResultOf(
            self.service.create(self.service.get(MY_VOLUME))
        )
        mount = volume.get_filesystem().get_path()
        mount.child(b'file').setContent(b'content')
        new_volume = self.successResultOf(
            volume.change_owner(self.other_node_id))
        new_mount = new_volume.get_filesystem().get_path()
        self.assertEqual(new_mount.child(b'file').getContent(), b'content')

    def test_enumerate(self):
        """
        The volumes returned from ``VolumeService.enumerate`` replace the old
        volume with the one returned by ``Volume.change_owner``.
        """
        volume = self.successResultOf(
            self.service.create(self.service.get(MY_VOLUME))
        )
        new_volume = self.successResultOf(
            volume.change_owner(self.other_node_id))
        volumes = set(self.successResultOf(self.service.enumerate()))
        self.assertEqual({new_volume}, volumes)


class VolumeScriptCreateVolumeServiceTests(SynchronousTestCase):
    """
    Tests for ``VolumeScript._create_volume_service``.
    """
    @skip_on_broken_permissions
    def test_exit(self):
        """
        ``VolumeScript._create_volume_service`` raises ``SystemExit`` with a
        non-zero code if ``VolumeService.startService`` raises
        ``CreateConfigurationError``.
        """
        directory = FilePath(self.mktemp())
        directory.makedirs()
        directory.chmod(0o000)
        self.addCleanup(directory.chmod, 0o777)
        config = directory.child("config.yml")

        stderr = StringIO()
        reactor = object()
        options = VolumeOptions()
        options.parseOptions([b"--config", config.path])
        with attempt_effective_uid('nobody', suppress_errors=True):
            exc = self.assertRaises(
                SystemExit, VolumeScript._create_volume_service,
                stderr, reactor, options)
        self.assertEqual(1, exc.code)

    @skip_on_broken_permissions
    def test_details_written(self):
        """
        ``VolumeScript._create_volume_service`` writes details of the error to
        the given ``stderr`` if ``VolumeService.startService`` raises
        ``CreateConfigurationError``.
        """
        directory = FilePath(self.mktemp())
        directory.makedirs()
        directory.chmod(0o000)
        self.addCleanup(directory.chmod, 0o777)
        config = directory.child("config.yml")

        stderr = StringIO()
        reactor = object()
        options = VolumeOptions()
        options.parseOptions([b"--config", config.path])
        with attempt_effective_uid('nobody', suppress_errors=True):
            self.assertRaises(
                SystemExit, VolumeScript._create_volume_service,
                stderr, reactor, options)
        self.assertEqual(
            "Writing config file {} failed: Permission denied\n".format(
                config.path).encode("ascii"),
            stderr.getvalue())

    def test_options(self):
        """
        When successful, ``VolumeScript._create_volume_service`` returns a
        running ``VolumeService`` initialized with the pool, mountpoint, and
        configuration path given by the ``options`` argument.
        """
        pool = b"some-pool"
        mountpoint = FilePath(self.mktemp())
        config = FilePath(self.mktemp())

        options = VolumeOptions()
        options.parseOptions([
            b"--config", config.path,
            b"--pool", pool,
            b"--mountpoint", mountpoint.path,
        ])

        stderr = StringIO()
        reactor = object()

        service = VolumeScript._create_volume_service(stderr, reactor, options)
        self.assertEqual(
            (True, config, StoragePool(reactor, pool, mountpoint)),
            (service.running, service._config_path, service.pool)
        )

    def test_service_factory(self):
        """
        ``VolumeScript._create_volume_service`` uses
        ``VolumeScript._service_factory`` to create a ``VolumeService`` (or
        whatever else that hook decides to create).
        """
        expected = Service()
        script = VolumeScript(object())
        self.patch(
            VolumeScript, "_service_factory",
            staticmethod(lambda config_path, pool, reactor: expected))

        options = VolumeOptions()
        options.parseOptions([])
        service = script._create_volume_service(
            object(), object(), options)
        self.assertIs(expected, service)


class VolumeScriptMainTests(SynchronousTestCase):
    """
    Tests for ``VolumeScript.main``.
    """
    def test_arguments(self):
        """
        ``VolumeScript.main`` calls the ``main`` method of the script object
        the ``VolumeScript`` was initialized with, passing the same reactor and
        options and also the running ``VolumeService``.
        """
        @implementer(ICommandLineVolumeScript)
        class VolumeServiceScript(object):
            def __init__(self):
                self.calls = []

            def main(self, reactor, options, volume_service):
                self.calls.append((reactor, options, volume_service))

        script = VolumeServiceScript()
        helper = VolumeScript(script)

        reactor = object()
        options = VolumeOptions()
        options.parseOptions([])

        service = Service()
        self.patch(
            VolumeScript, "_service_factory",
            staticmethod(lambda *args, **kwargs: service))

        helper.main(reactor, options)

        self.assertEqual(
            [(reactor, options, service)],
            script.calls
        )

    def test_default_stderr(self):
        """
        ``VolumeScript`` defaults to using the ``sys`` module.
        """
        self.assertIs(sys, VolumeScript(object())._sys_module)
