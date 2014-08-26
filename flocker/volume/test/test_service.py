# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""Tests for :module:`flocker.volume.service`."""

from __future__ import absolute_import

import json
from uuid import uuid4
from StringIO import StringIO

from zope.interface.verify import verifyObject

from twisted.application.service import IService
from twisted.internet.task import Clock
from twisted.python.filepath import FilePath, Permissions
from twisted.trial.unittest import SynchronousTestCase, TestCase

from ..service import (
    VolumeService, CreateConfigurationError, Volume,
    WAIT_FOR_VOLUME_INTERVAL, VolumeScript
    )
from ..script import VolumeOptions

from ..filesystems.memory import FilesystemStoragePool
from ..filesystems.zfs import StoragePool
from .._ipc import RemoteVolumeManager, LocalVolumeManager
from ..testtools import create_volume_service
from ...common import FakeNode
from ...testtools import skip_on_broken_permissions, attempt_effective_uid


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
        service = VolumeService(FilePath(self.mktemp()), None, reactor=Clock())
        service.startService()
        service2 = VolumeService(FilePath(self.mktemp()), None,
                                 reactor=Clock())
        service2.startService()
        self.assertNotEqual(service.uuid, service2.uuid)

    def test_no_config_written(self):
        """If no config file exists, a new one is written with the UUID."""
        path = FilePath(self.mktemp())
        service = VolumeService(path, None, reactor=Clock())
        service.startService()
        config = json.loads(path.getContent())
        self.assertEqual({u"uuid": service.uuid, u"version": 1}, config)

    def test_no_config_directory(self):
        """The config file's parent directory is created if it
        doesn't exist."""
        path = FilePath(self.mktemp()).child(b"config.json")
        service = VolumeService(path, None, reactor=Clock())
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
        service = VolumeService(path, None, reactor=Clock())
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
        service = VolumeService(path, None, reactor=Clock())
        with attempt_effective_uid('nobody', suppress_errors=True):
            self.assertRaises(CreateConfigurationError, service.startService)

    def test_config(self):
        """If a config file exists, the UUID is loaded from it."""
        path = self.mktemp()
        service = VolumeService(FilePath(path), None, reactor=Clock())
        service.startService()
        service2 = VolumeService(FilePath(path), None, reactor=Clock())
        service2.startService()
        self.assertEqual(service.uuid, service2.uuid)


class VolumeServiceAPITests(TestCase):
    """Tests for the ``VolumeService`` API."""

    def test_create_result(self):
        """``create()`` returns a ``Deferred`` that fires with a ``Volume``."""
        pool = FilesystemStoragePool(FilePath(self.mktemp()))
        service = VolumeService(FilePath(self.mktemp()), pool, reactor=Clock())
        service.startService()
        d = service.create(u"myvolume")
        self.assertEqual(
            self.successResultOf(d),
            Volume(uuid=service.uuid, name=u"myvolume", service=service))

    def test_create_filesystem(self):
        """``create()`` creates the volume's filesystem."""
        pool = FilesystemStoragePool(FilePath(self.mktemp()))
        service = VolumeService(FilePath(self.mktemp()), pool, reactor=Clock())
        service.startService()
        volume = self.successResultOf(service.create(u"myvolume"))
        self.assertTrue(pool.get(volume).get_path().isdir())

    @skip_on_broken_permissions
    def test_create_mode(self):
        """The created filesystem is readable/writable/executable by anyone.

        A better alternative will be implemented in
        https://github.com/ClusterHQ/flocker/issues/34
        """
        pool = FilesystemStoragePool(FilePath(self.mktemp()))
        service = VolumeService(FilePath(self.mktemp()), pool, reactor=Clock())
        service.startService()
        volume = self.successResultOf(service.create(u"myvolume"))
        self.assertEqual(pool.get(volume).get_path().getPermissions(),
                         Permissions(0777))

    def test_get(self):
        """
        ``VolumeService.get`` creates a ``Volume`` instance owned by that
        service and with given name.
        """
        service = create_volume_service(self)
        self.assertEqual(service.get(u"somevolume"),
                         Volume(uuid=service.uuid, name=u"somevolume",
                                service=service))

    def test_push_different_uuid(self):
        """Pushing a remotely-owned volume results in a ``ValueError``."""
        pool = FilesystemStoragePool(FilePath(self.mktemp()))
        service = VolumeService(FilePath(self.mktemp()), pool, reactor=Clock())
        service.startService()

        volume = Volume(uuid=u"wronguuid", name=u"blah", service=service)
        self.assertRaises(ValueError, service.push, volume,
                          RemoteVolumeManager(FakeNode()))

    def test_push_writes_filesystem(self):
        """Pushing a locally-owned volume writes its filesystem to the remote
        process."""
        pool = FilesystemStoragePool(FilePath(self.mktemp()))
        service = VolumeService(FilePath(self.mktemp()), pool, reactor=Clock())
        service.startService()
        volume = self.successResultOf(service.create(u"myvolume"))
        filesystem = volume.get_filesystem()
        filesystem.get_path().child(b"foo").setContent(b"blah")
        with filesystem.reader() as reader:
            data = reader.read()
        node = FakeNode()

        service.push(volume, RemoteVolumeManager(node))
        self.assertEqual(node.stdin.read(), data)

    def test_receive_local_uuid(self):
        """If a volume with same uuid as service is received, ``ValueError`` is
        raised."""
        pool = FilesystemStoragePool(FilePath(self.mktemp()))
        service = VolumeService(FilePath(self.mktemp()), pool, reactor=Clock())
        service.startService()

        self.assertRaises(ValueError, service.receive,
                          service.uuid.encode("ascii"), b"lalala", None)

    def test_receive_creates_volume(self):
        """Receiving creates a volume with the given uuid and name."""
        pool = FilesystemStoragePool(FilePath(self.mktemp()))
        service = VolumeService(FilePath(self.mktemp()), pool, reactor=Clock())
        service.startService()
        volume = self.successResultOf(service.create(u"myvolume"))
        filesystem = volume.get_filesystem()

        manager_uuid = unicode(uuid4())

        with filesystem.reader() as reader:
            service.receive(manager_uuid, u"newvolume", reader)
        new_volume = Volume(uuid=manager_uuid, name=u"newvolume",
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
        volume = self.successResultOf(service.create(u"myvolume"))
        filesystem = volume.get_filesystem()
        filesystem.get_path().child(b"afile").setContent(b"lalala")

        manager_uuid = unicode(uuid4())

        with filesystem.reader() as reader:
            service.receive(manager_uuid, u"newvolume", reader)

        new_volume = Volume(uuid=manager_uuid, name=u"newvolume",
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

    def test_enumerate_some_volumes(self):
        """``enumerate()`` returns all volumes previously ``create()``ed."""
        pool = FilesystemStoragePool(FilePath(self.mktemp()))
        service = VolumeService(FilePath(self.mktemp()), pool, reactor=Clock())
        service.startService()
        names = {u"somevolume", u"anotherone", u"lastone"}
        expected = {
            self.successResultOf(service.create(name))
            for name in names}
        service2 = VolumeService(FilePath(self.mktemp()), pool,
                                 reactor=Clock())
        service2.startService()
        actual = self.successResultOf(service2.enumerate())
        self.assertEqual(
            set((volume.uuid, volume.name) for volume in expected),
            set((volume.uuid, volume.name) for volume in actual))

    def test_enumerate_a_volume_with_period(self):
        """``enumerate()`` returns a volume previously ``create()``ed when its
        name includes a period."""
        pool = FilesystemStoragePool(FilePath(self.mktemp()))
        service = VolumeService(FilePath(self.mktemp()), pool, reactor=Clock())
        service.startService()
        expected = self.successResultOf(service.create(u"some.volume"))
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

        name = u"good volume name"
        self.successResultOf(service.create(name))

        volumes = list(self.successResultOf(service.enumerate()))
        self.assertEqual(
            [Volume(uuid=service.uuid, name=name, service=service)],
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

        self.failureResultOf(service.acquire(service.uuid, u"blah"),
                             ValueError)

    # Further tests for acquire() are done in
    # test_ipc.make_iremote_volume_manager.

    def test_handoff_rejects_remote_volume(self):
        """
        ``VolumeService.handoff()`` errbacks with a ``ValueError`` if given a
        remotely-owned volume.
        """
        service = create_volume_service(self)
        remote_volume = Volume(uuid=u"remote", name=u"blah",
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

        created = origin_service.create(u"avolume")

        def got_volume(volume):
            volume.get_filesystem().get_path().child(b"afile").setContent(
                b"exists")
            return origin_service.handoff(
                volume, LocalVolumeManager(destination_service))
        created.addCallback(got_volume)

        def handed_off(_):
            expected_volume = Volume(uuid=destination_service.uuid,
                                     name=u"avolume",
                                     service=destination_service)
            root = expected_volume.get_filesystem().get_path()
            self.assertEqual(root.child(b"afile").getContent(), b"exists")
        created.addCallback(handed_off)
        return created

    def test_handoff_changes_uuid(self):
        """
        ```VolumeService.handoff()`` changes the owner UUID of the local
        volume to the new owner's UUID.
        """
        origin_service = create_volume_service(self)
        destination_service = create_volume_service(self)

        created = origin_service.create(u"avolume")

        def got_volume(volume):
            return origin_service.handoff(
                volume, LocalVolumeManager(destination_service))
        created.addCallback(got_volume)
        created.addCallback(lambda _: origin_service.enumerate())

        def got_origin_volumes(volumes):
            expected_volume = Volume(uuid=destination_service.uuid,
                                     name=u"avolume",
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

        created = origin_service.create(u"avolume")

        def got_volume(volume):
            volume.get_filesystem().get_path().child(b"afile").setContent(
                b"exists")
            return origin_service.handoff(
                volume, LocalVolumeManager(destination_service))
        created.addCallback(got_volume)

        def handed_off(volumes):
            expected_volume = Volume(uuid=destination_service.uuid,
                                     name=u"avolume",
                                     service=origin_service)
            root = expected_volume.get_filesystem().get_path()
            self.assertEqual(root.child(b"afile").getContent(), b"exists")
        created.addCallback(handed_off)
        return created


class VolumeTests(TestCase):
    """Tests for ``Volume``."""

    def test_equality(self):
        """Volumes are equal if they have the same name, uuid and pool."""
        service = object()
        v1 = Volume(uuid=u"123", name=u"456", service=service)
        v2 = Volume(uuid=u"123", name=u"456", service=service)
        self.assertTrue(v1 == v2)
        self.assertFalse(v1 != v2)

    def test_inequality_uuid(self):
        """Volumes are unequal if they have different uuids."""
        service = object()
        v1 = Volume(uuid=u"123", name=u"456", service=service)
        v2 = Volume(uuid=u"123zz", name=u"456", service=service)
        self.assertTrue(v1 != v2)
        self.assertFalse(v1 == v2)

    def test_inequality_name(self):
        """Volumes are unequal if they have different names."""
        service = object()
        v1 = Volume(uuid=u"123", name=u"456", service=service)
        v2 = Volume(uuid=u"123", name=u"456zz", service=service)
        self.assertTrue(v1 != v2)
        self.assertFalse(v1 == v2)

    def test_inequality_pool(self):
        """Volumes are unequal if they have different pools."""
        v1 = Volume(uuid=u"123", name=u"456", service=object())
        v2 = Volume(uuid=u"123", name=u"456", service=object())
        self.assertTrue(v1 != v2)
        self.assertFalse(v1 == v2)

    def test_get_filesystem(self):
        """``Volume.get_filesystem`` returns the filesystem for the volume."""
        pool = FilesystemStoragePool(FilePath(self.mktemp()))
        service = VolumeService(FilePath(self.mktemp()), pool, None)
        volume = Volume(uuid=u"123", name=u"456", service=service)
        self.assertEqual(volume.get_filesystem(), pool.get(volume))

    def test_container_name(self):
        """
        The volume's container name adds ``"-data"`` suffix to the volume name.

        This ensures that geard will automatically mount it into a
        container whose name matches that of the volume.
        """
        volume = Volume(uuid=u"123", name=u"456", service=object())
        self.assertEqual(volume._container_name, b"456-data")

    def test_is_locally_owned(self):
        """
        ``Volume.locally_owned()`` indicates whether the volume's owner UUID
        matches that of the local volume manager.
        """
        service = create_volume_service(self)
        local = service.get(u"one")
        remote = Volume(uuid=service.uuid + u"extra", name=u"xxx",
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
        self.other_uuid = unicode(uuid4())

    def test_return(self):
        """
        ``Volume.change_owner`` returns a ``Deferred`` that fires with a new
        ``Volume`` with the new owner UUID and the same name.
        """
        volume = self.successResultOf(self.service.create(u"myvolume"))
        new_volume = self.successResultOf(volume.change_owner(self.other_uuid))
        self.assertEqual({'uuid': new_volume.uuid, 'name': new_volume.name},
                         {'uuid': self.other_uuid, 'name': u"myvolume"})

    def test_filesystem(self):
        """
        The filesystem for the new ``Volume`` preserves data from the old one.
        """
        volume = self.successResultOf(self.service.create(u"myvolume"))
        mount = volume.get_filesystem().get_path()
        mount.child(b'file').setContent(b'content')
        new_volume = self.successResultOf(volume.change_owner(self.other_uuid))
        new_mount = new_volume.get_filesystem().get_path()
        self.assertEqual(new_mount.child(b'file').getContent(), b'content')

    def test_enumerate(self):
        """
        The volumes returned from ``VolumeService.enumerate`` replace the old
        volume with the one returned by ``Volume.change_owner``.
        """
        volume = self.successResultOf(self.service.create(u"myvolume"))
        new_volume = self.successResultOf(volume.change_owner(self.other_uuid))
        volumes = set(self.successResultOf(self.service.enumerate()))
        self.assertEqual({new_volume}, volumes)


class WaitForVolumeTests(TestCase):
    """"
    Tests for ``VolumeService.wait_for_volume``.
    """

    def setUp(self):
        """
        Create a ``VolumeService`` pointing at a new pool.
        """
        self.clock = Clock()
        self.pool = FilesystemStoragePool(FilePath(self.mktemp()))
        self.service = VolumeService(FilePath(self.mktemp()), self.pool,
                                     reactor=self.clock)
        self.service.startService()

    def test_existing_volume(self):
        """
        If the volume already exists, the ``Deferred`` returned by
        ``VolumeService.wait_for_volume`` has already fired with the
        corresponding ``Volume``.
        """
        volume = self.successResultOf(self.service.create(u'volume'))
        wait = self.service.wait_for_volume(u'volume')
        self.assertEqual(self.successResultOf(wait), volume)

    def test_created_volume(self):
        """
        The ``Deferred`` returned by ``VolumeService.wait_for_volume`` fires
        with the corresponding ``Volume`` after the volume has been created.
        """
        wait = self.service.wait_for_volume(u'volume')
        volume = self.successResultOf(self.service.create(u'volume'))
        self.clock.advance(WAIT_FOR_VOLUME_INTERVAL)
        self.assertEqual(self.successResultOf(wait), volume)

    def test_late_created_volume(self):
        """
        The ``Deferred`` returned by ``VolumeService.wait_for_volume`` fires
        with the corresponding ``Volume`` after the volume has been created,
        even if the volume is unavailable after the first iteration.
        """
        wait = self.service.wait_for_volume(u'volume')
        self.clock.advance(WAIT_FOR_VOLUME_INTERVAL)
        volume = self.successResultOf(self.service.create(u'volume'))
        self.clock.advance(WAIT_FOR_VOLUME_INTERVAL)
        self.assertEqual(self.successResultOf(wait), volume)

    def test_no_volume(self):
        """
        If the volume doesn't exist, the ``Deferred`` returned by
        ``VolumeService.wait_for_volume`` has not fired.
        """
        self.assertNoResult(self.service.wait_for_volume(u'volume'))

    def test_remote_volume(self):
        """
        If the volume doesn't exist, the ``Deferred`` returned by
        The ``Deferred`` returned by ``VolumeService.wait_for_volume`` does not
        fire when a remote volume with the same name is received.
        """
        other_uuid = unicode(uuid4())
        remote_volume = Volume(uuid=other_uuid, name=u"volume",
                               service=self.service)
        self.successResultOf(self.pool.create(remote_volume))

        self.assertNoResult(self.service.wait_for_volume(u'volume'))


class VolumeScriptCreateVolumeServiceTests(SynchronousTestCase):
    """
    Tests for ``VolumeScript._create_volume_service``.
    """
    def test_exit(self):
        """
        ``VolumeScript._create_volume_service`` raises ``SystemExit`` with a
        non-zero code if ``VolumeService.startService`` raises
        ``CreateConfigurationError``.
        """
        stderr = StringIO()
        reactor = object()
        options = VolumeOptions()
        options.parseOptions([])
        exc = self.assertRaises(
            SystemExit, VolumeScript._create_volume_service,
            stderr, reactor, options)
        self.assertEqual((1,), exc.args)


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
