# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Testing utilities provided by ``flocker.volume``.
"""

import errno
import os
import uuid
from unittest import SkipTest

from characteristic import attributes

from twisted.python.filepath import FilePath
from twisted.internet.task import Clock
from twisted.internet import reactor
from twisted.trial.unittest import SynchronousTestCase

from ..common import ProcessNode
from ..testtools import run_process
from ._ipc import RemoteVolumeManager

from .filesystems.zfs import StoragePool
from .service import VolumeService
from .filesystems.memory import FilesystemStoragePool


def create_volume_service(test):
    """
    Create a new ``VolumeService`` suitable for use in unit tests.

    :param TestCase test: A unit test which will shut down the service
        when done.

    :return: The ``VolumeService`` created.
    """
    service = VolumeService(FilePath(test.mktemp()),
                            FilesystemStoragePool(FilePath(test.mktemp())),
                            reactor=Clock())
    service.startService()
    test.addCleanup(service.stopService)
    return service


def service_for_pool(test, pool):
    """
    Create a ``VolumeService`` wrapping a pool suitable for use in tests.

    :param TestCase test: A unit test which will shut down the service
        when done.
    :param IStoragePool pool: The pool to wrap.

    :return: A ``VolumeService``.
    """
    service = VolumeService(FilePath(test.mktemp()), pool, None)
    service.startService()
    test.addCleanup(service.stopService)
    return service


def create_zfs_pool(test_case):
    """Create a new ZFS pool, then delete it after the test is over.

    :param test_case: A ``unittest.TestCase``.

    :return: The pool's name as ``bytes``.
    """
    if os.getuid() != 0:
        raise SkipTest("Functional tests must run as root.")

    pool_name = b"testpool_%s" % (uuid.uuid4(),)
    pool_path = FilePath(test_case.mktemp())
    mount_path = FilePath(test_case.mktemp())
    with pool_path.open("wb") as f:
        f.truncate(100 * 1024 * 1024)
    test_case.addCleanup(pool_path.remove)
    try:
        run_process([b"zpool", b"create", b"-m", mount_path.path,
                     pool_name, pool_path.path])
    except OSError as e:
        if e.errno == errno.ENOENT:
            raise SkipTest(
                "Install zpool to run these tests: "
                "http://doc-dev.clusterhq.com/using/installing/index.html"
                "#optional-zfs-backend-configuration")

        raise
    test_case.addCleanup(run_process, [b"zpool", b"destroy", pool_name])
    return pool_name


class MutatingProcessNode(ProcessNode):
    """Mutate the command being run in order to make tests work.

    Come up with something better in
    https://clusterhq.atlassian.net/browse/FLOC-125
    """
    def __init__(self, to_service):
        """
        :param to_service: The VolumeService to which a push is being done.
        """
        self.to_service = to_service
        ProcessNode.__init__(self, initial_command_arguments=[])

    def _mutate(self, remote_command):
        """
        Add the pool and mountpoint arguments, which aren't necessary in real
        code.

        :param remote_command: Original command arguments.

        :return: Modified command arguments.
        """
        return remote_command[:1] + [
            b"--pool", self.to_service.pool._name,
            b"--mountpoint", self.to_service.pool._mount_root.path
        ] + remote_command[1:]

    def run(self, remote_command):
        return ProcessNode.run(self, self._mutate(remote_command))

    def get_output(self, remote_command):
        return ProcessNode.get_output(self, self._mutate(remote_command))


@attributes(["from_service", "to_service", "remote"])
class ServicePair(object):
    """
    A configuration for testing ``IRemoteVolumeManager``.

    :param VolumeService from_service: The origin service.
    :param VolumeService to_service: The destination service.
    :param IRemoteVolumeManager remote: Talks to ``to_service``.
    """


def create_realistic_servicepair(test):
    """
    Create a ``ServicePair`` that uses ZFS for testing
    ``RemoteVolumeManager``.

    :param TestCase test: A unit test.

    :return: A new ``ServicePair``.
    """
    from_pool = StoragePool(reactor, create_zfs_pool(test),
                            FilePath(test.mktemp()))
    from_service = VolumeService(FilePath(test.mktemp()),
                                 from_pool, reactor=Clock())
    from_service.startService()
    test.addCleanup(from_service.stopService)

    to_pool = StoragePool(reactor, create_zfs_pool(test),
                          FilePath(test.mktemp()))
    to_config = FilePath(test.mktemp())
    to_service = VolumeService(to_config, to_pool, reactor=Clock())
    to_service.startService()
    test.addCleanup(to_service.stopService)

    remote = RemoteVolumeManager(MutatingProcessNode(to_service),
                                 to_config)
    return ServicePair(from_service=from_service, to_service=to_service,
                       remote=remote)


def make_volume_options_tests(make_options, extra_arguments=None):
    """
    Make a ``TestCase`` to test the ``VolumeService`` specific arguments added
    to an ``Options`` class by the ``flocker_volume_options`` class decorator.

    :param make_options: A zero-argument callable which will be called to
        produce the ``Options`` instance under test.
    :param extra_arguments: An optional ``list`` of non-VolumeService related
        arguments which are required by the ``Options`` instance under test.
    :return: A ``SynchronousTestCase``.
    """
    if extra_arguments is None:
        extra_arguments = []

    def parseOptions(options, argv):
        options.parseOptions(argv + extra_arguments)

    class VolumeOptionsTests(SynchronousTestCase):
        """
        Tests for ``Options`` subclasses decorated with
        ``flocker_volume_options``.
        """
        def test_default_config(self):
            """
            By default the config file is ``b'/etc/flocker/volume.json'``.
            """
            options = make_options()
            parseOptions(options, [])
            self.assertEqual(
                FilePath(b"/etc/flocker/volume.json"), options["config"])

        def test_config(self):
            """
            The options class accepts a ``--config`` parameter.
            """
            path = b"/foo/bar"
            options = make_options()
            parseOptions(options, [b"--config", path])
            self.assertEqual(FilePath(path), options["config"])

        def test_pool(self):
            """
            The options class accepts a ``--pool`` parameter.
            """
            pool = b"foo-bar"
            options = make_options()
            parseOptions(options, [b"--pool", pool])
            self.assertEqual(pool, options["pool"])

        def test_mountpoint(self):
            """
            The options class accepts a ``--mountpoint`` parameter.
            """
            mountpoint = b"/bar/baz"
            options = make_options()
            parseOptions(options, [b"--mountpoint", mountpoint])
            self.assertEqual(mountpoint, options["mountpoint"])

    dummy_options = make_options()
    VolumeOptionsTests.__name__ = dummy_options.__class__.__name__ + "Tests"
    return VolumeOptionsTests
