# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""Unit tests for IPC."""

from __future__ import absolute_import

from unittest import TestCase as PyTestCase

from characteristic import attributes

from zope.interface.verify import verifyObject

from twisted.trial.unittest import TestCase
from twisted.python.filepath import FilePath

from ..service import VolumeService
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
            created = service_pair.from_service()

            def got_volume(volume):
                with self.assertRaises(RuntimeError):
                    with service_pair.remote.receive(volume):
                        raise RuntimeError()
            created.addCallback(got_volume)
            return created

    def test_receive_creates_volume(self):
        """``receive`` creates a volume."""
        created = self.from_service.create(u"thevolume")

        def do_push(volume):
            # Blocking call:
            run_locally = MutatingProcessNode(self.to_service)
            self.from_service.push(volume, run_locally, self.to_config)
        created.addCallback(do_push)

        def pushed(_):
            to_volume = Volume(uuid=self.from_service.uuid, name=u"thevolume",
                               _pool=self.to_pool)
            d = self.to_service.enumerate()

            def got_volumes(volumes):
                self.assertIn(to_volume, volumes)
            d.addCallback(got_volumes)
            return d
        created.addCallback(pushed)

        return created

    def test_creates_files(self):
        """``receive`` recreates files pushed from origin."""
        created = self.from_service.create(u"thevolume")

        def do_push(volume):
            root = volume.get_filesystem().get_path()
            root.child(b"afile.txt").setContent(b"WORKS!")

            # Blocking call:
            run_locally = MutatingProcessNode(self.to_service)
            self.from_service.push(volume, run_locally, self.to_config)
        created.addCallback(do_push)

        def pushed(_):
            to_volume = Volume(uuid=self.from_service.uuid, name=u"thevolume",
                               _pool=self.to_pool)
            root = to_volume.get_filesystem().get_path()
            self.assertEqual(root.child(b"afile.txt").getContent(), b"WORKS!")
        created.addCallback(pushed)

        return created

    return IRemoteVolumeManagerTests
