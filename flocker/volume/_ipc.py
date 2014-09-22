# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Inter-process communication for the volume manager.

Specific volume managers ("nodes") may wish to push data to other
nodes. In the current iteration this is done over SSH using a blocking
API. In some future iteration this will be replaced with an actual
well-specified communication protocol between daemon processes using
Twisted's event loop (https://github.com/ClusterHQ/flocker/issues/154).
"""

from contextlib import contextmanager
from io import BytesIO

from characteristic import with_cmp

from zope.interface import Interface, implementer

from twisted.internet.defer import succeed
from twisted.python.filepath import FilePath

from ..common._ipc import ProcessNode
from .service import DEFAULT_CONFIG_PATH
from .filesystems.zfs import Snapshot


# Path to SSH private key available on nodes and used to communicate
# across nodes.
# XXX duplicate of same information in flocker.cli:
# https://github.com/ClusterHQ/flocker/issues/390
SSH_PRIVATE_KEY_PATH = FilePath(b"/etc/flocker/id_rsa_flocker")


def standard_node(hostname):
    """
    Create the default production ``INode`` for the given hostname.

    That is, a node that SSHes as root to port 22 on the given hostname
    and authenticates using the cluster private key.

    :param bytes hostname: The host to connect to.
    :return: A ``INode`` that can connect to the given hostname using SSH.
    """
    return ProcessNode.using_ssh(hostname, 22, b"root", SSH_PRIVATE_KEY_PATH)


class IRemoteVolumeManager(Interface):
    """
    A remote volume manager with which one can communicate somehow.
    """
    def snapshots(volume):
        """
        Retrieve a list of the snapshots which exist for the given volume.

        :param Volume volume: The volume for which to retrieve snapshots.

        :return: A ``Deferred`` that fires with a ``list`` of ``Snapshot``
            instances giving the snapshot information.  The snapshots are
            ordered from oldest to newest.
        """

    def receive(volume):
        """
        Context manager that returns a file-like object to which a volume's
        contents can be written.

        :param Volume volume: The volume which will be pushed to the
            remote volume manager.

        :return: A file-like object that can be written to, which will
             update the volume on the remote volume manager.
        """

    def acquire(volume):
        """
        Tell the remote volume manager to acquire the given volume.

        :param Volume volume: The volume which will be acquired by the
            remote volume manager.

        :return: The UUID of the remote volume manager (as ``unicode``).
        """


@implementer(IRemoteVolumeManager)
@with_cmp(["_destination", "_config_path"])
class RemoteVolumeManager(object):
    """
    ``INode``\-based communication with a remote volume manager.
    """

    def __init__(self, destination, config_path=DEFAULT_CONFIG_PATH):
        """
        :param Node destination: The node to push to.
        :param FilePath config_path: Path to configuration file for the
            remote ``flocker-volume``.
        """
        self._destination = destination
        self._config_path = config_path

    def snapshots(self, volume):
        """
        Run ``flocker-volume snapshots`` on the destination and parse the
        output into a ``list`` of ``Snapshot`` instances.
        """
        data = self._destination.get_output(
            [b"flocker-volume",
             b"--config", self._config_path.path,
             b"snapshots",
             volume.uuid.encode("ascii"),
             volume.name.to_bytes()]
        )
        return succeed([
            Snapshot(name=name)
            for name
            in data.splitlines()
        ])

    def receive(self, volume):
        return self._destination.run([b"flocker-volume",
                                      b"--config", self._config_path.path,
                                      b"receive",
                                      volume.uuid.encode(b"ascii"),
                                      volume.name.to_bytes()])

    def acquire(self, volume):
        return self._destination.get_output(
            [b"flocker-volume",
             b"--config", self._config_path.path,
             b"acquire",
             volume.uuid.encode(b"ascii"),
             volume.name.to_bytes()]).decode("ascii")


@implementer(IRemoteVolumeManager)
class LocalVolumeManager(object):
    """
    In-memory communication with a ``VolumeService`` instance, for testing.
    """

    def __init__(self, service):
        """
        :param VolumeService service: The service to communicate with.
        """
        self._service = service

    def snapshots(self, volume):
        """
        Interrogate the volume's filesystem for its snapshots.
        """
        return volume.get_filesystem().snapshots()

    @contextmanager
    def receive(self, volume):
        input_file = BytesIO()
        yield input_file
        input_file.seek(0, 0)
        self._service.receive(volume.uuid, volume.name, input_file)

    def acquire(self, volume):
        self._service.acquire(volume.uuid, volume.name)
        return self._service.uuid
