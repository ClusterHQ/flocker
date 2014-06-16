# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""Volume manager service, the main entry point that manages volumes."""

from __future__ import absolute_import

import json
import stat
from uuid import uuid4

from characteristic import attributes

from twisted.application.service import Service


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
            filesystem.get_mountpoint().chmod(
                # 0o777 the long way:
                stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)
            return volume
        d.addCallback(created)
        return d

    def push(self, volume, destination):
        """Push the latest data in the volume to a remote destination.

        This is a blocking API, for now.

        :param Volume volume: The volume to push.
        :param Node destination: The node to push to.

        :return: ``Deferred`` that fires when the push is finished.
        """
        # fs = volume.get_filesystem()
        # contents = fs.get_contents()
        # receiver = destination.run([b"flocker-volume", b"receive",
        #                             volume.uuid.encode(b"ascii"),
        #                             volume.name.encode("ascii")])
        # for chunk in iter(lambda: contents.read(1024 * 1024), b""):
        #     receiver.write(chunk)
        # receiver.close()

    def receive(self, volume):
        """Process a volume's data that is being pushed in over stin.

        This is a blocking API, for now.

        :param Volume volume: A description of the volume being pushed in.
        """
        # receiver = self._pool.get_receiver(volume)
        # for chunk in iter(lambda: sys.stdin.read(1024 * 1024), b""):
        #     receiver.writer(chunk)
        # receiver.close()


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
