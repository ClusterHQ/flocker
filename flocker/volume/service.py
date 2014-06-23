# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""Volume manager service, the main entry point that manages volumes."""

from __future__ import absolute_import

import os
import json
import stat
from uuid import uuid4

from characteristic import attributes

from twisted.application.service import Service
from twisted.internet.endpoints import ProcessEndpoint, connectProtocol
from twisted.internet import reactor

# We might want to make these utilities shared, rather than in zfs
# module... but in this case the usage is temporary and should go away as
# part of https://github.com/hybridlogic/flocker/issues/64
from .filesystems.zfs import _AccumulatingProtocol, CommandFailed


class CreateConfigurationError(Exception):
    """Create the configuration file failed."""


class VolumeService(Service):
    """Main service for volume management.

    :ivar unicode uuid: A unique identifier for this particular node's
        volume manager. Only available once the service has started.
    """

    def __init__(self, config_path, pool):
        """
        :param FilePath config_path: Path to the volume manager config file.
        :param pool: A `flocker.volume.filesystems.interface.IStoragePool`
            provider.
        """
        self._config_path = config_path
        self._pool = pool

    def startService(self):
        parent = self._config_path.parent()
        try:
            if not parent.exists():
                parent.makedirs()
            if not self._config_path.exists():
                uuid = unicode(uuid4())
                self._config_path.setContent(json.dumps({u"uuid": uuid,
                                                         u"version": 1}))
        except OSError as e:
            raise CreateConfigurationError(e.args[1])
        config = json.loads(self._config_path.getContent())
        self.uuid = config[u"uuid"]

    def create(self, name):
        """Create a new volume.

        :param unicode name: The name of the volume.

        :return: A ``Deferred`` that fires with a :class:`Volume`.
        """
        volume = Volume(uuid=self.uuid, name=name, _pool=self._pool)
        d = self._pool.create(volume)
        def created(filesystem):
            filesystem.get_path().chmod(
                # 0o777 the long way:
                stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)
            return volume
        d.addCallback(created)
        return d

    def push(self, volume, destination):
        """Push the latest data in the volume to a remote destination.

        This is a blocking API, for now.

        Only locally owned volumes (i.e. volumes whose ``uuid`` matches
        this service's) can be pushed.

        :param Volume volume: The volume to push.
        :param Node destination: The node to push to.

        :raises ValueError: If the uuid of the volume is different than our own;
            only locally-owned volumes can be pushed.
        """
        if volume.uuid != self.uuid:
            raise ValueError()
        fs = volume.get_filesystem()
        with destination.run([b"flocker-volume", b"receive",
                              volume.uuid.encode(b"ascii"),
                              volume.name.encode("ascii")]) as receiver:
            with fs.reader() as contents:
                for chunk in iter(lambda: contents.read(1024 * 1024), b""):
                    receiver.write(chunk)

    def receive(self, volume_uuid, volume_name, input_file):
        """Process a volume's data that can be read from a file-lik.

        This is a blocking API, for now.

        Only remotely owned volumes (i.e. volumes whose ``uuid`` do not match
        this service's) can be received.

        :param unicode volume_uuid: The volume's UUID.

        :param unicode volume_name: The volume's name.

        :param input_file: A file-like object, typically ``sys.stdin``, from
            which to read the data.

        :raises ValueError: If the uuid of the volume matches our own;
            remote nodes can't overwrite locally-owned volumes.
        """
        if volume_uuid == self.uuid:
            raise ValueError()
        volume = Volume(uuid=volume_uuid, name=volume_name, _pool=self._pool)
        with volume.get_filesystem().writer() as writer:
             for chunk in iter(lambda: input_file.read(1024 * 1024), b""):
                 writer.write(chunk)


# Communication with Docker should be done via its API, not with this
# approach, but that depends on unreleased Twisted 14.1:
# https://github.com/hybridlogic/flocker/issues/64
def _docker_command(reactor, arguments):
    """Run the ``docker`` command-line tool with the given arguments.

    :param reactor: A ``IReactorProcess`` provider.

    :param arguments: A ``list`` of ``bytes``, command-line arguments to
    ``docker``.

    :return: A :class:`Deferred` firing with the bytes of the result (on
        exit code 0), or errbacking with :class:`CommandFailed` or
        :class:`BadArguments` depending on the exit code (1 or 2).
    """
    endpoint = ProcessEndpoint(reactor, b"docker", [b"docker"] + arguments,
                               os.environ)
    d = connectProtocol(endpoint, _AccumulatingProtocol())
    d.addCallback(lambda protocol: protocol._result)
    return d


@attributes(["uuid", "name", "_pool"])
class Volume(object):
    """A data volume's identifier.

    :ivar unicode uuid: The UUID of the volume manager that owns this volume.
    :ivar unicode name: The name of the volume. Since volume names must
        match Docker container names, the characters used should be limited to
        those that Docker allows for container names.
    :ivar _pool: A `flocker.volume.filesystems.interface.IStoragePool`
        provider where the volume's filesystem is stored.
    """
    def get_filesystem(self):
        """Return the volume's filesystem.

        :return: The ``IFilesystem`` provider for the volume.
        """
        return self._pool.get(self)

    @property
    def _container_name(self):
        """Return the corresponding Docker container name.

        :return: Container name as ``bytes``.
        """
        return b"flocker-%s-data" % (self.name.encode("ascii"),)

    def expose_to_docker(self, mount_path):
        """Create a container that will expose the volume to Docker at the given
        mount path.

        Can be called multiple times. Mount paths from previous calls will
        be overridden.

        :param mount_path: The path at which to mount the volume within
            the container.

        :return: ``Deferred`` firing when the operation is done.
        """
        local_path = self.get_filesystem().get_path().path
        mount_path = mount_path.path
        d = _docker_command(reactor, [b"rm", self._container_name])
        d.addErrback(lambda failure: failure.trap(CommandFailed))
        d.addCallback(lambda _: _docker_command(reactor,
                               [b"run", b"--name", self._container_name,
                                b"--volume=%s:%s:rw" % (local_path, mount_path),
                                b"busybox", b"/bin/true"]))
        return d
