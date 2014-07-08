# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""Unit tests for IPC."""

from __future__ import absolute_import

from unittest import TestCase as PyTestCase

from characteristic import attributes

from zope.interface.verify import verifyObject

from twisted.trial.unittest import TestCase
from twisted.python.filepath import FilePath

from ..service import VolumeService, Volume, DEFAULT_CONFIG_PATH
from ..filesystems.memory import FilesystemStoragePool
from .._ipc import (
    INode, FakeNode, IRemoteVolumeManager, RemoteVolumeManager,
    LocalVolumeManger,
    )
from ...testtools import assertNoFDsLeaked


def make_inode_tests(fixture):
    """
    Create a TestCase for ``INode``.

    :param fixture: A fixture that returns a :class:`INode` provider which
        will work with any arbitrary given command arguments.
    """
    class INodeTests(PyTestCase):
        """Tests for :class:`INode` implementors.

        May be functional tests depending on the fixture.
        """
        def test_interface(self):
            """
            The tested object provides :class:`INode`.
            """
            node = fixture(self)
            self.assertTrue(verifyObject(INode, node))

        def test_run_no_fd_leakage(self):
            """
            No file descriptors are leaked by ``run()``.
            """
            node = fixture(self)
            with assertNoFDsLeaked(self):
                with node.run([b"cat"]):
                    pass

        def test_run_exceptions_pass_through(self):
            """
            Exceptions raised in the context manager are not swallowed.
            """
            node = fixture(self)
            with self.assertRaises(RuntimeError):
                with node.run([b"cat"]):
                    raise RuntimeError()

        def test_run_no_fd_leakage_exceptions(self):
            """
            No file descriptors are leaked by ``run()`` if exception is
            raised within the context manager.
            """
            node = fixture(self)
            with assertNoFDsLeaked(self):
                try:
                    with node.run([b"cat"]):
                        raise RuntimeError()
                except RuntimeError:
                    pass

        def test_run_writeable(self):
            """
            The returned object from ``run()`` is writeable.
            """
            node = fixture(self)
            with node.run([b"python", b"-c",
                           b"import sys; sys.stdin.read()"]) as writer:
                writer.write(b"hello")
                writer.write(b"there")

        def test_get_output_no_leakage(self):
            """
            No file descriptors are leaked by ``get_output()``.
            """
            node = fixture(self)
            with assertNoFDsLeaked(self):
                node.get_output([b"echo", b"hello"])

        def test_get_output_result_bytes(self):
            """
            ``get_output()`` returns a result that is ``bytes``.
            """
            node = fixture(self)
            result = node.get_output([b"hello"])
            self.assertIsInstance(result, bytes)

    return INodeTests


class FakeINodeTests(make_inode_tests(lambda t: FakeNode([b"hello"]))):
    """``INode`` tests for ``FakeNode``."""


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
            """``receive`` creates a volume."""
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

    return IRemoteVolumeManagerTests


def create_local_servicepair(test):
    """
    Create a ``ServicePair`` allowing testing of ``LocalVolumeManger``.

    :param TestCase test: A unit test.

    :return: A new ``ServicePair``.
    """
    def create_service():
        path = FilePath(test.mktemp())
        path.createDirectory()
        pool = FilesystemStoragePool(path)
        service = VolumeService(FilePath(test.mktemp()), pool)
        service.startService()
        test.addCleanup(service.stopService)
        return service
    to_service = create_service()
    return ServicePair(from_service=create_service(), to_service=to_service,
                       remote=LocalVolumeManger(to_service))


class LocalVolumeManagerInterfaceTests(
        make_iremote_volume_manager(create_local_servicepair)):
    """
    Tests for ``LocalVolumeManger`` as a ``IRemoteVolumeManager``.
    """


class RemoteVolumeManagerTests(TestCase):
    """
    Tests for ``RemoteVolumeManager``.
    """
    def test_receive_destination_run(self):
        """
        Receiving calls ``flocker-volume`` remotely.
        """
        pool = FilesystemStoragePool(FilePath(self.mktemp()))
        service = VolumeService(FilePath(self.mktemp()), pool)
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
        service = VolumeService(FilePath(self.mktemp()), pool)
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

