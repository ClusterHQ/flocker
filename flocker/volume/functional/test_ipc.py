# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""Functional tests for IPC."""

import os
from unittest import skipIf

from twisted.internet import reactor
from twisted.internet.task import Clock
from twisted.python.filepath import FilePath

from .._ipc import RemoteVolumeManager
from ...common import ProcessNode
from ..service import VolumeService
from ..filesystems.zfs import StoragePool
from .test_filesystems_zfs import create_zfs_pool
from ..test.test_ipc import make_iremote_volume_manager, ServicePair

_if_root = skipIf(os.getuid() != 0, "Must run as root.")


class MutatingProcessNode(ProcessNode):
    """Mutate the command being run in order to make tests work.

    Come up with something better in
    https://github.com/ClusterHQ/flocker/issues/125
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
            b"--pool", self.to_service._pool._name,
            b"--mountpoint", self.to_service._pool._mount_root.path
        ] + remote_command[1:]

    def run(self, remote_command):
        return ProcessNode.run(self, self._mutate(remote_command))

    def get_output(self, remote_command):
        return ProcessNode.get_output(self, self._mutate(remote_command))


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


class RemoteVolumeManagerInterfaceTests(
        make_iremote_volume_manager(create_realistic_servicepair)):
    """
    Tests for ``RemoteVolumeManger`` as a ``IRemoteVolumeManager``.
    """
