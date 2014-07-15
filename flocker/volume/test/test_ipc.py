# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Unit tests for IPC.
"""

from __future__ import absolute_import

from characteristic import attributes

from zope.interface.verify import verifyObject

from twisted.internet.task import Clock
from twisted.python.filepath import FilePath
from twisted.trial.unittest import TestCase

from ..service import VolumeService, Volume, DEFAULT_CONFIG_PATH
from ..filesystems.memory import FilesystemStoragePool
from .._ipc import (
    IRemoteVolumeManager, RemoteVolumeManager, LocalVolumeManager)
from ...common import FakeNode


@attributes(["from_service", "to_service", "remote"])
class ServicePair(object):
    """
    A configuration for testing ``IRemoteVolumeManager``.

    :param VolumeService from_service: The origin service.
    :param VolumeService to_service: The destination service.
    :param IRemoteVolumeManager remote: Talks to ``to_service``.
    """


def make_iremote_volume_manager(fixture):
    """
    Create a TestCase for ``IRemoteVolumeManager``.

    :param fixture: A fixture that returns a :class:`ServicePair` instance.
    """
    class IRemoteVolumeManagerTests(TestCase):
        """
        Tests for ``IRemoteVolumeManager`` implementations.
        """
        def test_interface(self):
            """
            The tested object provides :class:`IRemoteVolumeManager`.
            """
            service_pair = fixture(self)
            self.assertTrue(verifyObject(IRemoteVolumeManager,
                                         service_pair.remote))

        def test_receive_exceptions_pass_through(self):
            """
            Exceptions raised in the ``receive()`` context manager are not
            swallowed.
            """
            service_pair = fixture(self)
            created = service_pair.from_service.create(u"newvolume")

            def got_volume(volume):
                with service_pair.remote.receive(volume):
                    raise RuntimeError()
            created.addCallback(got_volume)
            return self.assertFailure(created, RuntimeError)

        def test_receive_creates_volume(self):
            """
            ``receive`` creates a volume.
            """
            service_pair = fixture(self)
            created = service_pair.from_service.create(u"thevolume")

            def do_push(volume):
                with volume.get_filesystem().reader() as reader:
                    with service_pair.remote.receive(volume) as receiver:
                        receiver.write(reader.read())
            created.addCallback(do_push)

            def pushed(_):
                to_volume = Volume(uuid=service_pair.from_service.uuid,
                                   name=u"thevolume",
                                   _pool=service_pair.to_service._pool)
                d = service_pair.to_service.enumerate()

                def got_volumes(volumes):
                    self.assertIn(to_volume, list(volumes))
                d.addCallback(got_volumes)
                return d
            created.addCallback(pushed)

            return created

        def test_creates_files(self):
            """``receive`` recreates files pushed from origin."""
            service_pair = fixture(self)
            created = service_pair.from_service.create(u"thevolume")

            def do_push(volume):
                root = volume.get_filesystem().get_path()
                root.child(b"afile.txt").setContent(b"WORKS!")

                with volume.get_filesystem().reader() as reader:
                    with service_pair.remote.receive(volume) as receiver:
                        receiver.write(reader.read())
            created.addCallback(do_push)

            def pushed(_):
                to_volume = Volume(uuid=service_pair.from_service.uuid,
                                   name=u"thevolume",
                                   _pool=service_pair.to_service._pool)
                root = to_volume.get_filesystem().get_path()
                self.assertEqual(root.child(b"afile.txt").getContent(),
                                 b"WORKS!")
            created.addCallback(pushed)

            return created

        def remotely_owned_volume(self, service_pair):
            """
            Create a volume ``u"myvolume"`` on the origin service and a copy
            that is pushed to the destination service.

            :param ServicePair service_pair: The service pair.

            :return: The ``Volume`` instance on the origin service.
            """
            created = service_pair.from_service.create(u"myvolume")

            def got_volume(volume):
                service_pair.from_service.push(volume, service_pair.remote)
                return volume
            created.addCallback(got_volume)
            return created

        def test_acquire_changes_uuid(self):
            """
            ``acquire()`` changes the UUID of the given volume on the receiving
            side to the volume manager's.
            """
            service_pair = fixture(self)
            to_service = service_pair.to_service
            created = self.remotely_owned_volume(service_pair)

            def got_volume(pushed_volume):
                service_pair.remote.acquire(pushed_volume)
                d = to_service.enumerate()
                d.addCallback(lambda results: self.assertEqual(
                    list(results),
                    [Volume(uuid=to_service.uuid, name=pushed_volume.name,
                            _pool=to_service._pool)]))
                return d
            created.addCallback(got_volume)
            return created

        def test_acquire_preserves_data(self):
            """
            ``acquire()`` preserves the data from the acquired volume in the
            renamed volume.
            """
            service_pair = fixture(self)
            to_service = service_pair.to_service
            created = self.remotely_owned_volume(service_pair)

            def got_volume(pushed_volume):
                root = pushed_volume.get_filesystem().get_path()
                root.child(b"test").setContent(b"some data")
                # Re-push with updated contents:
                service_pair.from_service.push(pushed_volume,
                                               service_pair.remote)

                service_pair.remote.acquire(pushed_volume)

                filesystem = Volume(uuid=to_service.uuid,
                                    name=pushed_volume.name,
                                    _pool=to_service._pool).get_filesystem()
                new_root = filesystem.get_path()
                self.assertEqual(new_root.child(b"test").getContent(),
                                 b"some data")
            created.addCallback(got_volume)
            return created

        def test_acquire_returns_uuid(self):
            """
            ``acquire()`` returns the UUID of the remote volume manager.
            """
            service_pair = fixture(self)
            to_service = service_pair.to_service
            created = self.remotely_owned_volume(service_pair)

            def got_volume(pushed_volume):
                result = service_pair.remote.acquire(pushed_volume)
                self.assertEqual(result, to_service.uuid)
            created.addCallback(got_volume)
            return created

    return IRemoteVolumeManagerTests


def create_local_servicepair(test):
    """
    Create a ``ServicePair`` allowing testing of ``LocalVolumeManager``.

    :param TestCase test: A unit test.

    :return: A new ``ServicePair``.
    """
    def create_service():
        path = FilePath(test.mktemp())
        path.createDirectory()
        pool = FilesystemStoragePool(path)
        service = VolumeService(FilePath(test.mktemp()), pool, reactor=Clock())
        service.startService()
        test.addCleanup(service.stopService)
        return service
    to_service = create_service()
    return ServicePair(from_service=create_service(), to_service=to_service,
                       remote=LocalVolumeManager(to_service))


class LocalVolumeManagerInterfaceTests(
        make_iremote_volume_manager(create_local_servicepair)):
    """
    Tests for ``LocalVolumeManager`` as a ``IRemoteVolumeManager``.
    """


class RemoteVolumeManagerTests(TestCase):
    """
    Tests for ``RemoteVolumeManager``.
    """
    def test_receive_destination_run(self):
        """
        Receiving calls ``flocker-volume`` remotely with ``receive`` command.
        """
        pool = FilesystemStoragePool(FilePath(self.mktemp()))
        service = VolumeService(FilePath(self.mktemp()), pool, reactor=Clock())
        service.startService()
        volume = self.successResultOf(service.create(u"myvolume"))
        node = FakeNode()

        remote = RemoteVolumeManager(node, FilePath(b"/path/to/json"))
        with remote.receive(volume):
            pass
        self.assertEqual(node.remote_command,
                         [b"flocker-volume", b"--config", b"/path/to/json",
                          b"receive", volume.uuid.encode("ascii"),
                          b"myvolume"])

    def test_receive_default_config(self):
        """
        ``RemoteVolumeManager`` by default calls ``flocker-volume`` with
        default config path.
        """
        pool = FilesystemStoragePool(FilePath(self.mktemp()))
        service = VolumeService(FilePath(self.mktemp()), pool, reactor=Clock())
        service.startService()
        volume = self.successResultOf(service.create(u"myvolume"))
        node = FakeNode()

        remote = RemoteVolumeManager(node)
        with remote.receive(volume):
            pass
        self.assertEqual(node.remote_command,
                         [b"flocker-volume", b"--config",
                          DEFAULT_CONFIG_PATH.path,
                          b"receive", volume.uuid.encode("ascii"),
                          b"myvolume"])

    def test_acquire_destination_run(self):
        """
        ``RemoteVolumeManager.acquire()`` calls ``flocker-volume`` remotely
        with ``acquire`` command.
        """
        pool = FilesystemStoragePool(FilePath(self.mktemp()))
        service = VolumeService(FilePath(self.mktemp()), pool, reactor=Clock())
        service.startService()
        volume = self.successResultOf(service.create(u"myvolume"))
        node = FakeNode([b"remoteuuid"])

        remote = RemoteVolumeManager(node, FilePath(b"/path/to/json"))
        remote.acquire(volume)

        self.assertEqual(node.remote_command,
                         [b"flocker-volume", b"--config", b"/path/to/json",
                          b"acquire", volume.uuid.encode("ascii"),
                          b"myvolume"])
