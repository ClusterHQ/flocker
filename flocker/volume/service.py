# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
# -*- test-case-name: flocker.volume.test.test_service -*-

"""
Volume manager service, the main entry point that manages volumes.
"""

from __future__ import absolute_import

import sys
import json
import stat
from uuid import UUID, uuid4

from zope.interface import Interface, implementer

from characteristic import attributes

from twisted.internet.defer import maybeDeferred
from twisted.python.filepath import FilePath
from twisted.application.service import Service
from twisted.internet.defer import fail

# We might want to make these utilities shared, rather than in zfs
# module... but in this case the usage is temporary and should go away as
# part of https://clusterhq.atlassian.net/browse/FLOC-64
from .filesystems.zfs import StoragePool
from ._model import VolumeSize
from ..common.script import ICommandLineScript

DEFAULT_CONFIG_PATH = FilePath(b"/etc/flocker/volume.json")
FLOCKER_MOUNTPOINT = FilePath(b"/flocker")
FLOCKER_POOL = b"flocker"

WAIT_FOR_VOLUME_INTERVAL = 0.1


class CreateConfigurationError(Exception):
    """Create the configuration file failed."""


@attributes(["namespace", "dataset_id"])
class VolumeName(object):
    """
    The volume and its copies' name within the cluster.

    :ivar unicode namespace: The namespace of the volume,
        e.g. ``u"default"``. Must not include periods.

    :ivar unicode dataset_id: The unique id of the dataset. It is not
        expected to be meaningful to humans. Since volume ids must match
        Docker container names, the characters used should be limited to
        those that Docker allows for container names (``[a-zA-Z0-9_.-]``).
    """
    def __init__(self):
        """
        :raises ValueError: If a period is included in the namespace.
        """
        if u"." in self.namespace:
            raise ValueError(
                "Periods not allowed in namespace: %s"
                % (self.namespace,))

    @classmethod
    def from_bytes(cls, name):
        """
        Create ``VolumeName`` from its byte representation.

        :param bytes name: The name, output of ``VolumeName.to_bytes``
            call in past.

        :raises ValueError: If parsing the bytes failed.

        :return: Corresponding ``VolumeName``.
        """
        namespace, identifier = name.split(b'.', 1)
        return VolumeName(namespace=namespace.decode("ascii"),
                          dataset_id=identifier.decode("ascii"))

    def to_bytes(self):
        """
        Convert the name to ``bytes``.

        :return: ``VolumeName`` encoded as bytes that can be read by
            ``VolumeName.from_bytes``.
        """
        return b"%s.%s" % (self.namespace.encode("ascii"),
                           self.dataset_id.encode("ascii"))


class VolumeService(Service):
    """
    Main service for volume management.

    This should really use the node UUID rather than having its own config
    for that. https://clusterhq.atlassian.net/browse/FLOC-1885


    :ivar unicode node_id: A unique identifier for this particular node's
        volume manager. Only available once the service has started.
    """

    def __init__(self, config_path, pool, reactor):
        """
        :param FilePath config_path: Path to the volume manager config file.
        :param pool: An object that is both a
            ``flocker.volume.filesystems.interface.IStoragePool`` provider
            and a ``twisted.application.service.IService`` provider.
        :param reactor: A ``twisted.internet.interface.IReactorTime`` provider.
        """
        self._config_path = config_path
        self.pool = pool
        self._reactor = reactor

    def startService(self):
        Service.startService(self)
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
        self.node_id = config[u"uuid"]
        self.pool.startService()

    def create(self, volume):
        """
        Create a new volume.

        :param Volume volume: The ``Volume`` instance to create in the service
            storage pool.

        :return: A ``Deferred`` that fires with a :class:`Volume`.
        """
        # XXX Consider changing the type of volume to a volume model object.
        # FLOC-1062
        d = self.pool.create(volume)

        def created(filesystem):
            self._make_public(filesystem)
            return volume
        d.addCallback(created)
        return d

    def set_maximum_size(self, volume):
        """
        Resize an existing volume.

        :param Volume volume: The ``Volume`` instance to resize in the storage
            pool.

        :return: A ``Deferred`` that fires with a :class:`Volume`.
        """
        d = self.pool.set_maximum_size(volume)

        def resized(filesystem):
            return volume
        d.addCallback(resized)
        return d

    def clone_to(self, parent, name):
        """
        Clone a parent ``Volume`` to create a new one.

        :param Volume parent: The volume to clone.

        :param VolumeName name: The name of the volume to clone to.

        :return: A ``Deferred`` that fires with a :class:`Volume`.
        """
        volume = self.get(name)
        d = self.pool.clone_to(parent, volume)

        def created(filesystem):
            self._make_public(filesystem)
            return volume
        d.addCallback(created)
        return d

    def _make_public(self, filesystem):
        """
        Make a filesystem publically readable/writeable/executable.

        A better alternative will be implemented in
        https://clusterhq.atlassian.net/browse/FLOC-34

        :param filesystem: A ``IFilesystem`` provider.
        """
        filesystem.get_path().chmod(
            # 0o777 the long way:
            stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)

    def get(self, name, **kwargs):
        """
        Return a locally-owned ``Volume`` with the given name.

        Whether or not this volume actually exists is not checked in any way.

        :param **: Additional keyword arguments to pass on to the ``Volume``
            initializer.

        :param VolumeName name: The name of the volume.

        :param node_id: Either ``None``, in which case the local node ID
            will be used, or a ``unicode`` node ID to use for the volume.

        :return: A ``Volume``.
        """
        return Volume(node_id=self.node_id, name=name, service=self, **kwargs)

    def enumerate(self):
        """Get a listing of all volumes managed by this service.

        :return: A ``Deferred`` that fires with an iterator of :class:`Volume`.
        """
        enumerating = self.pool.enumerate()

        def enumerated(filesystems):
            for filesystem in filesystems:
                # XXX It so happens that this works but it's kind of a
                # fragile way to recover the information:
                #    https://clusterhq.atlassian.net/browse/FLOC-78
                basename = filesystem.get_path().basename()
                try:
                    node_id, name = basename.split(b".", 1)
                    name = VolumeName.from_bytes(name)
                    # We convert to a UUID object for validation purposes:
                    UUID(node_id)
                except ValueError:
                    # ValueError may happen because:
                    # 1. We can't split on `.`.
                    # 2. We couldn't parse the UUID.
                    # 3. We couldn't parse the volume name.
                    # In any of those case it's presumably because that's
                    # not a filesystem Flocker is managing.Perhaps a user
                    # created it, so we just ignore it.
                    continue

                # Probably shouldn't yield this volume if the uuid doesn't
                # match this service's uuid.

                yield Volume(
                    node_id=node_id.decode("ascii"),
                    name=name,
                    service=self,
                    size=filesystem.size)
        enumerating.addCallback(enumerated)
        return enumerating

    def push(self, volume, destination):
        """
        Push the latest data in the volume to a remote destination.

        This is a blocking API for now.

        Only locally owned volumes (i.e. volumes whose ``uuid`` matches
        this service's) can be pushed.

        :param Volume volume: The volume to push.

        :param IRemoteVolumeManager destination: The remote volume manager
            to push to.

        :raises ValueError: If the uuid of the volume is different than
            our own; only locally-owned volumes can be pushed.
        """
        if volume.node_id != self.node_id:
            raise ValueError()
        fs = volume.get_filesystem()
        getting_snapshots = destination.snapshots(volume)

        def got_snapshots(snapshots):
            with destination.receive(volume) as receiver:
                with fs.reader(snapshots) as contents:
                    for chunk in iter(lambda: contents.read(1024 * 1024), b""):
                        receiver.write(chunk)

        pushing = getting_snapshots.addCallback(got_snapshots)
        return pushing

    def receive(self, volume_node_id, volume_name, input_file):
        """
        Process a volume's data that can be read from a file-like object.

        This is a blocking API for now.

        Only remotely owned volumes (i.e. volumes whose ``uuid`` do not match
        this service's) can be received.

        :param unicode volume_node_id: The volume's owner's node ID.
        :param VolumeName volume_name: The volume's name.
        :param input_file: A file-like object, typically ``sys.stdin``, from
            which to read the data.

        :raises ValueError: If the uuid of the volume matches our own;
            remote nodes can't overwrite locally-owned volumes.
        """
        if volume_node_id == self.node_id:
            raise ValueError()
        volume = Volume(node_id=volume_node_id, name=volume_name, service=self)
        with volume.get_filesystem().writer() as writer:
            for chunk in iter(lambda: input_file.read(1024 * 1024), b""):
                writer.write(chunk)

    def acquire(self, volume_node_id, volume_name):
        """
        Take ownership of a volume.

        This is a blocking API for now.

        Only remotely owned volumes (i.e. volumes whose ``uuid`` do not match
        this service's) can be acquired.

        :param unicode volume_node_id: The volume's owner's node ID.
        :param VolumeName volume_name: The volume's name.

        :return: ``Deferred`` that fires on success, or errbacks with
            ``ValueError`` If the uuid of the volume matches our own.
        """
        if volume_node_id == self.node_id:
            return fail(ValueError("Can't acquire already-owned volume"))
        volume = Volume(node_id=volume_node_id, name=volume_name, service=self)
        return volume.change_owner(self.node_id)

    def handoff(self, volume, destination):
        """
        Handoff a locally owned volume to a remote destination.

        The remote destination will be the new owner of the volume.

        This is a blocking API for now (but it does return a ``Deferred``
        for success/failure).

        :param Volume volume: The volume to handoff.
        :param IRemoteVolumeManager destination: The remote volume manager
            to handoff to.

        :return: ``Deferred`` that fires when the handoff has finished, or
            errbacks on error (specifcally with a ``ValueError`` if the
            volume is not locally owned).
        """
        pushing = maybeDeferred(self.push, volume, destination)

        def pushed(ignored):
            remote_uuid = destination.acquire(volume)
            return volume.change_owner(remote_uuid)
        changing_owner = pushing.addCallback(pushed)
        return changing_owner


@attributes(["node_id", "name", "service", "size"],
            defaults=dict(size=VolumeSize(maximum_size=None)))
class Volume(object):
    """
    A data volume's identifier.

    :ivar unicode node_id: The node ID of the volume manager that owns
        this volume.
    :ivar VolumeName name: The name of the volume.
    :ivar VolumeSize size: The storage capacity of the volume.
    :ivar VolumeService service: The service that stores this volume.
    """
    def locally_owned(self):
        """
        Return whether this volume is locally owned.

        :return: ``True`` if volume's owner is the ``VolumeService`` that
            is storing it, otherwise ``False``.
        """
        return self.node_id == self.service.node_id

    def change_owner(self, new_owner_id):
        """
        Change which volume manager owns this volume.

        :param unicode new_owner_id: The node ID of the new owner.

        :return: ``Deferred`` that fires with a new :class:`Volume`
            instance once the ownership has been changed.
        """
        new_volume = Volume(node_id=new_owner_id, name=self.name,
                            service=self.service, size=self.size)
        d = self.service.pool.change_owner(self, new_volume)

        def filesystem_changed(_):
            return new_volume
        d.addCallback(filesystem_changed)
        return d

    def get_filesystem(self):
        """Return the volume's filesystem.

        :return: The ``IFilesystem`` provider for the volume.
        """
        return self.service.pool.get(self)


@implementer(ICommandLineScript)
class VolumeScript(object):
    """
    ``VolumeScript`` is a command line script helper which creates and starts a
    ``VolumeService`` and then makes it available to another object which
    implements the rest of the behavior for the command line script.

    :ivar _service_factory: ``VolumeService`` by default but can be
        overridden for testing purposes.
    """
    _service_factory = VolumeService

    @classmethod
    def _create_volume_service(cls, stderr, reactor, options):
        """
        Create a ``VolumeService`` for the given arguments.

        :return: The started ``VolumeService``.
        """
        pool = StoragePool(reactor, options["pool"],
                           FilePath(options["mountpoint"]))
        service = cls._service_factory(
            config_path=options["config"], pool=pool, reactor=reactor)
        try:
            service.startService()
        except CreateConfigurationError as e:
            stderr.write(
                b"Writing config file %s failed: %s\n" % (
                    options["config"].path, e)
            )
            raise SystemExit(1)
        return service

    def __init__(self, volume_script, sys_module=sys):
        """
        :param ICommandLineVolumeScript volume_script: Another script
            implementation which will be passed a started ``VolumeService``
            along with the reactor and script options.
        """
        self._volume_script = volume_script
        self._sys_module = sys_module

    def main(self, reactor, options):
        """
        Create and start the ``VolumeService`` and then delegate the rest to
        the other script object that this object was initialized with.
        """
        service = self._create_volume_service(
            self._sys_module.stderr, reactor, options)
        return self._volume_script.main(reactor, options, service)


class ICommandLineVolumeScript(Interface):
    """
    A script which requires a running ``VolumeService`` and can be run by
    ``FlockerScriptRunner`` and `VolumeScript``.
    """
    def main(reactor, options, volume_service):
        """
        :param VolumeService volume_service: An already-started volume service.

        See ``ICommandLineScript.main`` for documentation for the other
        parameters and return value.
        """
