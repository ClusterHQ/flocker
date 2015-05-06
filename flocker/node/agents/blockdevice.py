# -*- test-case-name: flocker.node.agents.test.test_blockdevice -*-
# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
This module implements the parts of a block-device based dataset
convergence agent that can be re-used against many different kinds of block
devices.
"""

from errno import EEXIST
from uuid import UUID
from subprocess import check_output

from eliot import MessageType, ActionType, Field, Logger
from eliot.serializers import identity

from zope.interface import implementer, Interface

from pyrsistent import PRecord, field
from characteristic import attributes, with_cmp

import psutil
from bitmath import Byte

from twisted.internet.defer import succeed, fail
from twisted.python.filepath import FilePath

from .. import (
    IDeployer, IStateChange, sequentially, in_parallel, run_state_change
)
from ...control import NodeState, Manifestation, Dataset, NonManifestDatasets
from ...common import auto_threaded


# Eliot is transitioning away from the "Logger instances all over the place"
# approach.  And it's hard to put Logger instances on PRecord subclasses which
# we have a lot of.  So just use this global logger for now.
_logger = Logger()


@attributes(["dataset_id"])
class DatasetWithoutVolume(Exception):
    """
    An operation was attempted on a dataset that involves manipulating the
    dataset's volume but that volume could not be found.

    :ivar UUID dataset_id: The unique identifier of the dataset the operation
        was meant to affect.
    """


class VolumeException(Exception):
    """
    A base class for exceptions raised by  ``IBlockDeviceAPI`` operations.

    :param unicode blockdevice_id: The unique identifier of the block device.
    """
    def __init__(self, blockdevice_id):
        if not isinstance(blockdevice_id, unicode):
            raise TypeError(
                'Unexpected blockdevice_id type. '
                'Expected unicode. '
                'Got {!r}.'.format(blockdevice_id)
            )
        Exception.__init__(self, blockdevice_id)
        self.blockdevice_id = blockdevice_id


class UnknownVolume(VolumeException):
    """
    The block device could not be found.
    """


class AlreadyAttachedVolume(VolumeException):
    """
    A failed attempt to attach a block device that is already attached.
    """


class UnattachedVolume(VolumeException):
    """
    An attempt was made to operate on an unattached volume but the operation
    requires the volume to be attached.
    """

OLD_SIZE = Field.for_types(
    u"old_size", [int], u"The size of a volume prior to a resize operation."
)

NEW_SIZE = Field.for_types(
    u"new_size", [int],
    u"The intended size of a volume after resize operation."
)

DATASET = Field(
    u"dataset",
    lambda dataset: dataset.dataset_id,
    u"The unique identifier of a dataset."
)

VOLUME = Field(
    u"volume",
    lambda volume: volume.blockdevice_id,
    u"The unique identifier of a volume."
)

FILESYSTEM_TYPE = Field.forTypes(
    u"filesystem_type",
    [unicode],
    u"The name of a filesystem."
)

DATASET_ID = Field(
    u"dataset_id",
    lambda dataset_id: unicode(dataset_id),
    u"The unique identifier of a dataset."
)

MOUNTPOINT = Field(
    u"mountpoint",
    lambda path: path.path,
    u"The absolute path to the location on the node where the dataset will be "
    u"mounted.",
)

DEVICE_PATH = Field(
    u"block_device_path",
    lambda path: path.path,
    u"The absolute path to the block device file on the node where the "
    u"dataset is attached.",
)

BLOCK_DEVICE_ID = Field(
    u"block_device_id",
    lambda id: unicode(id),
    u"The unique identifier if the underlying block device."
)

BLOCK_DEVICE_SIZE = Field(
    u"block_device_size",
    identity,
    u"The size of the underlying block device."
)

BLOCK_DEVICE_HOST = Field(
    u"block_device_host",
    identity,
    u"The host to which the underlying block device is attached."
)

BLOCK_DEVICE_PATH = Field(
    u"block_device_path",
    lambda path: path.path,
    u"The system device file for an attached block device."
)

CREATE_BLOCK_DEVICE_DATASET = ActionType(
    u"agent:blockdevice:create",
    [DATASET, MOUNTPOINT],
    [],
    u"A block-device-backed dataset is being created.",
)

# Really this is the successful completion of CREATE_BLOCK_DEVICE_DATASET.  It
# might be nice if these fields could just be added to the running action
# instead of being logged as a separate message (but still in the correct
# context).  Or maybe this is fine as-is.
BLOCK_DEVICE_DATASET_CREATED = MessageType(
    u"agent:blockdevice:created",
    [DEVICE_PATH, BLOCK_DEVICE_ID, DATASET_ID, BLOCK_DEVICE_SIZE,
     BLOCK_DEVICE_HOST],
    u"A block-device-backed dataset has been created.",
)

DESTROY_BLOCK_DEVICE_DATASET = ActionType(
    u"agent:blockdevice:destroy",
    [DATASET_ID],
    [],
    u"A block-device-backed dataset is being destroyed.",
)

UNMOUNT_BLOCK_DEVICE = ActionType(
    u"agent:blockdevice:unmount",
    [DATASET_ID],
    [],
    u"A block-device-backed dataset is being unmounted.",
)

UNMOUNT_BLOCK_DEVICE_DETAILS = MessageType(
    u"agent:blockdevice:unmount:details",
    [VOLUME, BLOCK_DEVICE_PATH],
    u"The device file for a block-device-backed dataset has been discovered."
)

MOUNT_BLOCK_DEVICE = ActionType(
    u"agent:blockdevice:mount",
    [DATASET_ID],
    [],
    u"A block-device-backed dataset is being mounted.",
)

MOUNT_BLOCK_DEVICE_DETAILS = MessageType(
    u"agent:blockdevice:mount:details",
    [VOLUME, BLOCK_DEVICE_PATH],
    u"The device file for a block-device-backed dataset has been discovered."
)

ATTACH_VOLUME = ActionType(
    u"agent:blockdevice:attach_volume",
    [DATASET_ID],
    [],
    u"The volume for a block-device-backed dataset is being attached."
)

ATTACH_VOLUME_DETAILS = MessageType(
    u"agent:blockdevice:attach_volume:details",
    [VOLUME],
    u"The volume for a block-device-backed dataset has been discovered."
)

DETACH_VOLUME = ActionType(
    u"agent:blockdevice:detach_volume",
    [DATASET_ID],
    [],
    u"The volume for a block-device-backed dataset is being detached."
)

DETACH_VOLUME_DETAILS = MessageType(
    u"agent:blockdevice:detach_volume:details",
    [VOLUME],
    u"The volume for a block-device-backed dataset has been discovered."
)

DESTROY_VOLUME = ActionType(
    u"agent:blockdevice:destroy_volume",
    [VOLUME],
    [],
    u"The volume for a block-device-backed dataset is being destroyed."
)

RESIZE_VOLUME = ActionType(
    u"agent:blockdevice:resize_volume",
    [VOLUME, OLD_SIZE, NEW_SIZE],
    [],
    u"The volume for a block-device-backed dataset is being resized."
)

CREATE_FILESYSTEM = ActionType(
    u"agent:blockdevice:create_filesystem",
    [VOLUME, FILESYSTEM_TYPE],
    [],
    u"A block device is being initialized with a filesystem.",
)

RESIZE_FILESYSTEM = ActionType(
    u"agent:blockdevice:resize_filesystem",
    [VOLUME],
    [],
    u"The filesystem on a block-device-backed dataset is being resized."
)

RESIZE_BLOCK_DEVICE_DATASET = ActionType(
    u"agent:blockdevice:resize",
    [DATASET_ID],
    [],
    u"A block-device-backed dataset is being resized.",
)


def _volume_field():
    """
    Create and return a ``PRecord`` ``field`` to hold a ``BlockDeviceVolume``.
    """
    return field(
        type=BlockDeviceVolume, mandatory=True,
        # Disable the automatic PRecord.create factory.  Callers can just
        # supply the right type, we don't need the magic coercion behavior
        # supplied by default.
        factory=lambda x: x
    )


class BlockDeviceVolume(PRecord):
    """
    A block device that may be attached to a host.

    :ivar unicode blockdevice_id: An identifier for the block device which is
        unique across the entire cluster.  For example, an EBS volume
        identifier (``vol-4282672b``).  This is used to address the block
        device for operations like attach and detach.
    :ivar int size: The size, in bytes, of the block device.
    :ivar unicode host: The IP address of the host to which the block device is
        attached or ``None`` if it is currently unattached.
    :ivar UUID dataset_id: The Flocker dataset ID associated with this volume.
    """
    blockdevice_id = field(type=unicode, mandatory=True)
    size = field(type=int, mandatory=True)
    host = field(type=(unicode, type(None)), initial=None)
    dataset_id = field(type=UUID, mandatory=True)


def _blockdevice_volume_from_datasetid(volumes, dataset_id):
    """
    A helper to get the volume for a given dataset_id.

    :param list volumes: The ``BlockDeviceVolume`` instances to inspect for a
        match.
    :param UUID dataset_id: The identifier of the dataset the volume of which
        to find.

    :return: Either a ``BlockDeviceVolume`` matching the given ``dataset_id``
        or ``None`` if no such volume can be found.
    """
    for volume in volumes:
        if volume.dataset_id == dataset_id:
            return volume


# Get rid of this in favor of calculating each individual operation in
# BlockDeviceDeployer.calculate_changes.  FLOC-1772
@implementer(IStateChange)
class DestroyBlockDeviceDataset(PRecord):
    """
    Destroy the volume for a dataset with a primary manifestation on the node
    where this state change runs.

    :ivar UUID dataset_id: The unique identifier of the dataset to which the
        volume to be destroyed belongs.
    """
    dataset_id = field(type=UUID, mandatory=True)

    # This can be replaced with a regular attribute when the `_logger` argument
    # is no longer required by Eliot.
    @property
    def eliot_action(self):
        return DESTROY_BLOCK_DEVICE_DATASET(
            _logger, dataset_id=self.dataset_id
        )

    def run(self, deployer):
        volume = _blockdevice_volume_from_datasetid(
            deployer.block_device_api.list_volumes(), self.dataset_id
        )
        if volume is None:
            return succeed(None)

        return run_state_change(
            sequentially(
                changes=[
                    UnmountBlockDevice(dataset_id=self.dataset_id),
                    DetachVolume(dataset_id=self.dataset_id),
                    DestroyVolume(volume=volume),
                ]
            ),
            deployer,
        )


@implementer(IStateChange)
class ResizeVolume(PRecord):
    """
    Change the size of a volume.

    :ivar BlockDeviceVolume volume: The volume to resize.
    :ivar int size: The size (in bytes) to which to resize the volume.
    """
    volume = _volume_field()
    size = field(type=int, mandatory=True)

    @property
    def eliot_action(self):
        return RESIZE_VOLUME(
            _logger, volume=self.volume,
            old_size=self.volume.size, new_size=self.size,
        )

    def run(self, deployer):
        deployer.block_device_api.resize_volume(
            self.volume.blockdevice_id, self.size
        )
        return succeed(None)


@implementer(IStateChange)
class CreateFilesystem(PRecord):
    """
    Create a filesystem on a block device.

    :ivar BlockDeviceVolume volume: The volume in which to create the
        filesystem.
    :ivar unicode filesystem: The name of the filesystem type to create.  For
        example, ``u"ext4"``.
    """
    volume = _volume_field()
    filesystem = field(type=unicode, mandatory=True)

    @property
    def eliot_action(self):
        return CREATE_FILESYSTEM(
            _logger, volume=self.volume, filesystem=self.filesystem
        )

    def run(self, deployer):
        device = deployer.block_device_api.get_device_path(
            self.volume.blockdevice_id
        )
        check_output([
            b"mkfs", b"-t", self.filesystem.encode("ascii"), device.path
        ])
        return succeed(None)


def _valid_size(size):
    """
    Pyrsistent invariant for filesystem size, which must be a multiple of 1024
    bytes.
    """
    if size % 1024 == 0:
        return (True, "")
    return (
        False, "Filesystem size must be multiple of 1024, not %d" % (size,)
    )


@implementer(IStateChange)
class ResizeFilesystem(PRecord):
    """
    Resize the filesystem on a volume.

    This is currently limited to growing the filesystem to exactly the size of
    the volume.

    :ivar BlockDeviceVolume volume: The volume with an existing filesystem to
        resize.
    """
    volume = _volume_field()

    size = field(
        type=int, mandatory=True,
        # It would be nice to compute this invariant from the API schema.
        invariant=_valid_size,
    )

    @property
    def eliot_action(self):
        return RESIZE_FILESYSTEM(_logger, volume=self.volume)

    def run(self, deployer):
        device = deployer.block_device_api.get_device_path(
            self.volume.blockdevice_id
        )
        # resize2fs gets angry at us without an e2fsck pass first.  This is
        # unfortunate because we don't really want to make random filesystem
        # fixes at this point (there should really be nothing to fix).  This
        # may merit further consideration.
        #
        # -f forces the check to run even if the filesystem appears "clean"
        #     (which it ought to because we haven't corrupted it, just resized
        #     the block device).
        #
        # -y automatically answers yes to every question.  There should be no
        #     questions since the filesystem isn't corrupt.  Without this,
        #     e2fsck refuses to run non-interactively, though.
        #
        # See FLOC-1814
        check_output([b"e2fsck", b"-f", b"-y", device.path])
        # When passed no explicit size argument, resize2fs resizes the
        # filesystem to the size of the device it lives on.  Be sure to use
        # 1024 byte KiB conversion because that's what "K" means to resize2fs.
        # This will be come out as an integer because the API schema requires
        # multiples of 1024 bytes for dataset sizes.  However, it would be nice
        # the API schema could be informed by the backend somehow so that other
        # constraints could be applied as well (for example, OpenStack volume
        # sizes are in GB - so if you're using that the API should really
        # require multiples of 1000000000).  See FLOC-1579.
        new_size = int(Byte(self.size).to_KiB().value)
        # The system could fail while this is running.  We don't presently have
        # recovery logic for this case.  See FLOC-1815.
        check_output([
            b"resize2fs",
            # The path to the device file referring to the filesystem to
            # resize.
            device.path,
            # The desired new size of that filesystem in units of 1024 bytes.
            u"{}K".format(new_size).encode("ascii"),
        ])
        return succeed(None)


# Get rid of this in favor of calculating each individual operation in
# BlockDeviceDeployer.calculate_changes.  FLOC-1773
@implementer(IStateChange)
# Make them sort reasonably for ease of testing and because determinism is
# generally pretty nice.
@with_cmp(["dataset_id", "size"])
class ResizeBlockDeviceDataset(PRecord):
    """
    Resize the volume for a dataset with a primary manifestation on the node
    where this state change runs.

    :ivar UUID dataset_id: The unique identifier of the dataset to which the
        volume to be destroyed belongs.
    :ivar int size: The size (in bytes) to which to resize the block device.
    """
    dataset_id = field(type=UUID, mandatory=True)
    size = field(type=int, mandatory=True)

    @property
    def eliot_action(self):
        return RESIZE_BLOCK_DEVICE_DATASET(_logger, dataset_id=self.dataset_id)

    def run(self, deployer):
        volume = _blockdevice_volume_from_datasetid(
            deployer.block_device_api.list_volumes(), self.dataset_id
        )
        attach = AttachVolume(
            dataset_id=self.dataset_id, hostname=deployer.hostname
        )
        mount = MountBlockDevice(
            dataset_id=self.dataset_id,
            mountpoint=deployer._mountpath_for_dataset_id(
                unicode(self.dataset_id)
            )
        )
        unmount = UnmountBlockDevice(dataset_id=self.dataset_id)
        detach = DetachVolume(dataset_id=self.dataset_id)

        resize_filesystem = ResizeFilesystem(volume=volume, size=self.size)
        resize_volume = ResizeVolume(volume=volume, size=self.size)
        if self.size < volume.size:
            changes = [
                unmount,
                resize_filesystem,
                detach,
                resize_volume,
                attach,
                mount,
            ]
        else:
            changes = [
                unmount,
                detach,
                resize_volume,
                attach,
                resize_filesystem,
                mount,
            ]

        return run_state_change(sequentially(changes=changes), deployer)


@implementer(IStateChange)
class MountBlockDevice(PRecord):
    """
    Mount the filesystem mounted from the block device backed by a particular
    volume.

    :ivar UUID dataset_id: The unique identifier of the dataset associated with
        the filesystem to mount.
    :ivar FilePath mountpoint: The filesystem location at which to mount the
        volume's filesystem.  If this does not exist, it is created.
    """
    dataset_id = field(type=UUID, mandatory=True)
    mountpoint = field(type=FilePath, mandatory=True)

    @property
    def eliot_action(self):
        return MOUNT_BLOCK_DEVICE(_logger, dataset_id=self.dataset_id)

    def run(self, deployer):
        """
        Run the system ``mount`` tool to mount this change's volume's block
        device.  The volume must be attached to this node.
        """
        api = deployer.block_device_api
        volume = _blockdevice_volume_from_datasetid(
            api.list_volumes(), self.dataset_id
        )
        device = api.get_device_path(volume.blockdevice_id)
        MOUNT_BLOCK_DEVICE_DETAILS(
            volume=volume, block_device_path=device,
        ).write(_logger)

        try:
            self.mountpoint.makedirs()
        except OSError as e:
            if EEXIST != e.errno:
                return fail()
        # This should be asynchronous.  FLOC-1797
        check_output([b"mount", device.path, self.mountpoint.path])
        return succeed(None)


@implementer(IStateChange)
class UnmountBlockDevice(PRecord):
    """
    Unmount the filesystem mounted from the block device backed by a particular
    volume.

    :ivar UUID dataset_id: The unique identifier of the dataset associated with
        the filesystem to unmount.
    """
    dataset_id = field(type=UUID, mandatory=True)

    @property
    def eliot_action(self):
        return UNMOUNT_BLOCK_DEVICE(_logger, dataset_id=self.dataset_id)

    def run(self, deployer):
        """
        Run the system ``unmount`` tool to unmount this change's volume's block
        device.  The volume must be attached to this node and the corresponding
        block device mounted.
        """
        api = deployer.async_block_device_api
        listing = api.list_volumes()
        listing.addCallback(
            _blockdevice_volume_from_datasetid, self.dataset_id
        )

        def found(volume):
            if volume is None:
                # It was not actually found.
                raise DatasetWithoutVolume(dataset_id=self.dataset_id)
            d = api.get_device_path(volume.blockdevice_id)
            d.addCallback(lambda device: (volume, device))
            return d
        listing.addCallback(found)

        def got_device((volume, device)):
            UNMOUNT_BLOCK_DEVICE_DETAILS(
                volume=volume, block_device_path=device
            ).write(_logger)
            # This should be asynchronous. FLOC-1797
            check_output([b"umount", device.path])
        listing.addCallback(got_device)
        return listing


@implementer(IStateChange)
class AttachVolume(PRecord):
    """
    Attach an unattached volume to a node.

    :ivar UUID dataset_id: The unique identifier of the dataset associated with
        the volume to attach.
    :ivar unicode hostname: An identifier for the node to which the volume
        should be attached.  An IPv4 address literal.
    """
    dataset_id = field(type=UUID, mandatory=True)
    hostname = field(type=unicode, mandatory=True)

    @property
    def eliot_action(self):
        return ATTACH_VOLUME(_logger, dataset_id=self.dataset_id)

    def run(self, deployer):
        """
        Use the deployer's ``IBlockDeviceAPI`` to attach the volume.
        """
        api = deployer.async_block_device_api
        listing = api.list_volumes()
        listing.addCallback(
            _blockdevice_volume_from_datasetid, self.dataset_id
        )

        def found(volume):
            if volume is None:
                # It was not actually found.
                raise DatasetWithoutVolume(dataset_id=self.dataset_id)
            ATTACH_VOLUME_DETAILS(volume=volume).write(_logger)
            return api.attach_volume(volume.blockdevice_id, self.hostname)
        attaching = listing.addCallback(found)
        return attaching


@implementer(IStateChange)
class DetachVolume(PRecord):
    """
    Detach a volume from the node it is currently attached to.

    :ivar UUID dataset_id: The unique identifier of the dataset associated with
        the volume to detach.
    """
    dataset_id = field(type=UUID, mandatory=True)

    @property
    def eliot_action(self):
        return DETACH_VOLUME(_logger, dataset_id=self.dataset_id)

    def run(self, deployer):
        """
        Use the deployer's ``IBlockDeviceAPI`` to detach the volume.
        """
        api = deployer.async_block_device_api
        listing = api.list_volumes()
        listing.addCallback(
            _blockdevice_volume_from_datasetid, self.dataset_id
        )

        def found(volume):
            if volume is None:
                # It was not actually found.
                raise DatasetWithoutVolume(dataset_id=self.dataset_id)
            DETACH_VOLUME_DETAILS(volume=volume).write(_logger)
            return api.detach_volume(volume.blockdevice_id)
        detaching = listing.addCallback(found)
        return detaching


@implementer(IStateChange)
class DestroyVolume(PRecord):
    """
    Destroy the storage (and therefore contents) of a volume.

    :ivar BlockDeviceVolume volume: The volume to destroy.
    """
    volume = _volume_field()

    @property
    def eliot_action(self):
        return DESTROY_VOLUME(_logger, volume=self.volume)

    def run(self, deployer):
        """
        Use the deployer's ``IBlockDeviceAPI`` to destroy the volume.
        """
        # Make this asynchronous as part of FLOC-1549.
        deployer.block_device_api.destroy_volume(self.volume.blockdevice_id)
        return succeed(None)


# Get rid of this in favor of calculating each individual operation in
# BlockDeviceDeployer.calculate_changes.  FLOC-1771
@implementer(IStateChange)
class CreateBlockDeviceDataset(PRecord):
    """
    An operation to create a new dataset on a newly created volume with a newly
    initialized filesystem.

    :ivar Dataset dataset: The dataset for which to create a block device.
    :ivar FilePath mountpoint: The path at which to mount the created device.
    """
    dataset = field(mandatory=True, type=Dataset)
    mountpoint = field(mandatory=True, type=FilePath)

    @property
    def eliot_action(self):
        return CREATE_BLOCK_DEVICE_DATASET(
            _logger,
            dataset=self.dataset, mountpoint=self.mountpoint
        )

    def run(self, deployer):
        """
        Create a block device, attach it to the local host, create an ``ext4``
        filesystem on the device and mount it.

        Operations are performed synchronously.

        See ``IStateChange.run`` for general argument and return type
        documentation.

        :returns: An already fired ``Deferred`` with result ``None``.
        """
        api = deployer.block_device_api
        volume = api.create_volume(
            dataset_id=UUID(self.dataset.dataset_id),
            size=self.dataset.maximum_size,
        )

        # This duplicates AttachVolume now.
        volume = api.attach_volume(
            volume.blockdevice_id, deployer.hostname
        )
        device = api.get_device_path(volume.blockdevice_id)

        # This duplicates CreateFilesystem now.
        check_output(["mkfs", "-t", "ext4", device.path])

        # This duplicates MountBlockDevice now.
        self.mountpoint.makedirs()
        check_output(["mount", device.path, self.mountpoint.path])

        BLOCK_DEVICE_DATASET_CREATED(
            block_device_path=device,
            block_device_id=volume.blockdevice_id,
            dataset_id=volume.dataset_id,
            block_device_size=volume.size,
            block_device_host=volume.host,
        ).write(_logger)
        return succeed(None)


class IBlockDeviceAsyncAPI(Interface):
    """
    Common operations provided by all block device backends, exposed via
    asynchronous methods.
    """
    def create_volume(dataset_id, size):
        """
        See ``IBlockDeviceAPI.create_volume``.

        :returns: A ``Deferred`` that fires with a ``BlockDeviceVolume`` when
            the volume has been created.
        """

    def destroy_volume(blockdevice_id):
        """
        See ``IBlockDeviceAPI.destroy_volume``.

        :return: A ``Deferred`` that fires when the volume has been destroyed.
        """

    def attach_volume(blockdevice_id, host):
        """
        See ``IBlockDeviceAPI.attach_volume``.

        :returns: A ``Deferred`` that fires with a ``BlockDeviceVolume`` with a
            ``host`` attribute set to ``host``.
        """

    def detach_volume(blockdevice_id):
        """
        See ``BlockDeviceAPI.detach_volume``.

        :returns: A ``Deferred`` that fires when the volume has been detached.
        """

    def resize_volume(blockdevice_id, size):
        """
        See ``BlockDeviceAPI.resize_volume``.

        :returns: A ``Deferred`` that fires when the volume has been resized.
        """

    def list_volumes():
        """
        See ``BlockDeviceAPI.list_volume``.

        :returns: A ``Deferred`` that fires with a ``list`` of
            ``BlockDeviceVolume``\ s.
        """

    def get_device_path(blockdevice_id):
        """
        See ``BlockDeviceAPI.get_device_path``.

        :returns: A ``Deferred`` that fires with a ``FilePath`` for the device.
        """


class IBlockDeviceAPI(Interface):
    """
    Common operations provided by all block device backends, exposed via
    synchronous methods.

    Note: This is an early sketch of the interface and it'll be refined as we
    real blockdevice providers are implemented.
    """
    def create_volume(dataset_id, size):
        """
        Create a new volume.

        XXX: Probably needs to be some checking of valid sizes for different
        backends. Perhaps the allowed sizes should be defined as constants?

        :param UUID dataset_id: The Flocker dataset ID of the dataset on this
            volume.
        :param int size: The size of the new volume in bytes.
        :returns: A ``BlockDeviceVolume``.
        """

    def destroy_volume(blockdevice_id):
        """
        Destroy an existing volume.

        :param unicode blockdevice_id: The unique identifier for the volume to
            destroy.

        :raises UnknownVolume: If the supplied ``blockdevice_id`` does not
            exist.

        :return: ``None``
        """

    def attach_volume(blockdevice_id, host):
        """
        Attach ``blockdevice_id`` to ``host``.

        :param unicode blockdevice_id: The unique identifier for the block
            device being attached.
        :param unicode host: The IP address of a host to attach the volume to.
        :raises UnknownVolume: If the supplied ``blockdevice_id`` does not
            exist.
        :raises AlreadyAttachedVolume: If the supplied ``blockdevice_id`` is
            already attached.
        :returns: A ``BlockDeviceVolume`` with a ``host`` attribute set to
            ``host``.
        """

    def detach_volume(blockdevice_id):
        """
        Detach ``blockdevice_id`` from whatever host it is attached to.

        :param unicode blockdevice_id: The unique identifier for the block
            device being detached.

        :raises UnknownVolume: If the supplied ``blockdevice_id`` does not
            exist.
        :raises UnattachedVolume: If the supplied ``blockdevice_id`` is
            not attached to anything.
        :returns: ``None``
        """

    def resize_volume(blockdevice_id, size):
        """
        Resize an unattached ``blockdevice_id``.

        This changes the amount of storage available.  It does not change the
        data on the volume (including the filesystem).

        :param unicode blockdevice_id: The unique identifier for the block
            device being detached.
        :param int size: The required size, in bytes, of the volume.

        :raises UnknownVolume: If the supplied ``blockdevice_id`` does not
            exist.

        :returns: ``None``
        """

    def list_volumes():
        """
        List all the block devices available via the back end API.

        :returns: A ``list`` of ``BlockDeviceVolume``s.
        """

    def get_device_path(blockdevice_id):
        """
        Return the device path that has been allocated to the block device on
        the host to which it is currently attached.

        :param unicode blockdevice_id: The unique identifier for the block
            device.
        :raises UnknownVolume: If the supplied ``blockdevice_id`` does not
            exist.
        :raises UnattachedVolume: If the supplied ``blockdevice_id`` is
            not attached to a host.
        :returns: A ``FilePath`` for the device.
        """


@implementer(IBlockDeviceAsyncAPI)
@auto_threaded(IBlockDeviceAPI, "_reactor", "_sync", "_threadpool")
class _SyncToThreadedAsyncAPIAdapter(PRecord):
    """
    Adapt any ``IBlockDeviceAPI`` to ``IBlockDeviceAsyncAPI`` by running its
    methods in threads of a thread pool.
    """
    _reactor = field()
    _sync = field()
    _threadpool = field()


def _blockdevicevolume_from_dataset_id(dataset_id, size, host=None):
    """
    Create a new ``BlockDeviceVolume`` with a ``blockdevice_id`` derived
    from the given ``dataset_id``.

    This is for convenience of implementation of the loopback backend (to
    avoid needing a separate data store for mapping dataset ids to block
    device ids and back again).

    Parameters accepted have the same meaning as the attributes of
    ``BlockDeviceVolume``.
    """
    return BlockDeviceVolume(
        size=size, host=host, dataset_id=dataset_id,
        blockdevice_id=u"block-{0}".format(dataset_id),
    )


def _blockdevicevolume_from_blockdevice_id(blockdevice_id, size, host=None):
    """
    Create a new ``BlockDeviceVolume`` with a ``dataset_id`` derived from
    the given ``blockdevice_id``.

    This reverses the transformation performed by
    ``_blockdevicevolume_from_dataset_id``.

    Parameters accepted have the same meaning as the attributes of
    ``BlockDeviceVolume``.
    """
    # Strip the "block-" prefix we added.
    dataset_id = UUID(blockdevice_id[6:])
    return BlockDeviceVolume(
        size=size, host=host, dataset_id=dataset_id,
        blockdevice_id=blockdevice_id,
    )


def _losetup_list_parse(output):
    """
    Parse the output of ``losetup --all`` which varies depending on the
    privileges of the user.

    :param unicode output: The output of ``losetup --all``.
    :returns: A ``list`` of
        2-tuple(FilePath(device_file), FilePath(backing_file))
    """
    devices = []
    for line in output.splitlines():
        parts = line.split(u":", 2)
        if len(parts) != 3:
            continue
        device_file, attributes, backing_file = parts
        device_file = FilePath(device_file.strip().encode("utf-8"))

        # Trim everything from the first left bracket, skipping over the
        # possible inode number which appears only when run as root.
        left_bracket_offset = backing_file.find(b"(")
        backing_file = backing_file[left_bracket_offset + 1:]

        # Trim everything from the right most right bracket
        right_bracket_offset = backing_file.rfind(b")")
        backing_file = backing_file[:right_bracket_offset]

        # Trim a possible embedded deleted flag
        expected_suffix_list = [b"(deleted)"]
        for suffix in expected_suffix_list:
            offset = backing_file.rfind(suffix)
            if offset > -1:
                backing_file = backing_file[:offset]

        # Remove the space that may have been between the path and the deleted
        # flag.
        backing_file = backing_file.rstrip()
        backing_file = FilePath(backing_file.encode("utf-8"))
        devices.append((device_file, backing_file))
    return devices


def _losetup_list():
    """
    List all the loopback devices on the system.

    :returns: A ``list`` of
        2-tuple(FilePath(device_file), FilePath(backing_file))
    """
    output = check_output(
        ["losetup", "--all"]
    ).decode('utf8')
    return _losetup_list_parse(output)


def _device_for_path(expected_backing_file):
    """
    :param FilePath backing_file: A path which may be associated with a
        loopback device.
    :returns: A ``FilePath`` to the loopback device if one is found, or
        ``None`` if no device exists.
    """
    for device_file, backing_file in _losetup_list():
        if expected_backing_file == backing_file:
            return device_file


@implementer(IBlockDeviceAPI)
class LoopbackBlockDeviceAPI(object):
    """
    A simulated ``IBlockDeviceAPI`` which creates loopback devices backed by
    files located beneath the supplied ``root_path``.
    """
    _attached_directory_name = 'attached'
    _unattached_directory_name = 'unattached'

    def __init__(self, root_path):
        """
        :param FilePath root_path: The path beneath which all loopback backing
            files and their organising directories will be created.
        """
        self._root_path = root_path

    @classmethod
    def from_path(cls, root_path):
        """
        :param bytes root_path: The path to a directory in which loop back
            backing files will be created. The directory is created if it does
            not already exist.
        :returns: A ``LoopbackBlockDeviceAPI`` with the supplied ``root_path``.
        """
        api = cls(root_path=FilePath(root_path))
        api._initialise_directories()
        return api

    def _initialise_directories(self):
        """
        Create the root and sub-directories in which loopback files will be
        created.
        """
        self._unattached_directory = self._root_path.child(
            self._unattached_directory_name)

        try:
            self._unattached_directory.makedirs()
        except OSError:
            pass

        self._attached_directory = self._root_path.child(
            self._attached_directory_name)

        try:
            self._attached_directory.makedirs()
        except OSError:
            pass

    def create_volume(self, dataset_id, size):
        """
        Create a "sparse" file of some size and put it in the ``unattached``
        directory.

        See ``IBlockDeviceAPI.create_volume`` for parameter and return type
        documentation.
        """
        volume = _blockdevicevolume_from_dataset_id(
            size=size, dataset_id=dataset_id,
        )
        with self._unattached_directory.child(
            volume.blockdevice_id.encode('ascii')
        ).open('wb') as f:
            f.truncate(size)
        return volume

    def destroy_volume(self, blockdevice_id):
        """
        Destroy the storage for the given unattached volume.
        """
        volume = self._get(blockdevice_id)
        volume_path = self._unattached_directory.child(
            volume.blockdevice_id.encode("ascii")
        )
        volume_path.remove()

    def _get(self, blockdevice_id):
        for volume in self.list_volumes():
            if volume.blockdevice_id == blockdevice_id:
                return volume
        raise UnknownVolume(blockdevice_id)

    def attach_volume(self, blockdevice_id, host):
        """
        Move an existing ``unattached`` file into a per-host directory and
        create a loopback device backed by that file.

        Note: Although `mkfs` can format files directly and `mount` can mount
        files directly (with the `-o loop` option), we want to simulate a real
        block device which will be allocated a real block device file on the
        host to which it is attached. This allows the consumer of this API to
        perform formatting and mount operations exactly the same as for a real
        block device.

        See ``IBlockDeviceAPI.attach_volume`` for parameter and return type
        documentation.
        """
        volume = self._get(blockdevice_id)
        if volume.host is None:
            old_path = self._unattached_directory.child(blockdevice_id)
            host_directory = self._attached_directory.child(
                host.encode("utf-8")
            )
            try:
                host_directory.makedirs()
            except OSError:
                pass
            new_path = host_directory.child(blockdevice_id)
            old_path.moveTo(new_path)
            # The --find option allocates the next available /dev/loopX device
            # name to the device.
            check_output(["losetup", "--find", new_path.path])
            attached_volume = volume.set(host=host)
            return attached_volume

        raise AlreadyAttachedVolume(blockdevice_id)

    def detach_volume(self, blockdevice_id):
        """
        Move an existing file from a per-host directory into the ``unattached``
        directory and release the loopback device backed by that file.
        """
        volume = self._get(blockdevice_id)
        if volume.host is None:
            raise UnattachedVolume(blockdevice_id)

        # ``losetup --detach`` only if the file was used for a loop device.
        if self.get_device_path(blockdevice_id) is not None:
            check_output([
                b"losetup", b"--detach",
                self.get_device_path(blockdevice_id).path
            ])

        volume_path = self._attached_directory.descendant([
            volume.host.encode("ascii"), volume.blockdevice_id.encode("ascii")
        ])
        new_path = self._unattached_directory.child(
            volume.blockdevice_id.encode("ascii")
        )
        volume_path.moveTo(new_path)

    def resize_volume(self, blockdevice_id, size):
        """
        Change the size of the loopback backing file.

        Sparseness is maintained by using ``truncate`` on the backing file.

        This implementation is limited to being able to resize volumes only if
        they are unattached.
        """
        backing_path = self._unattached_directory.child(
            blockdevice_id.encode("ascii")
        )
        try:
            backing_file = backing_path.open("r+")
        except IOError:
            raise UnknownVolume(blockdevice_id)
        else:
            try:
                backing_file.truncate(size)
            finally:
                backing_file.close()

    def list_volumes(self):
        """
        Return ``BlockDeviceVolume`` instances for all the files in the
        ``unattached`` directory and all per-host directories.

        See ``IBlockDeviceAPI.list_volumes`` for parameter and return type
        documentation.
        """
        volumes = []
        for child in self._root_path.child('unattached').children():
            blockdevice_id = child.basename().decode('ascii')
            volume = _blockdevicevolume_from_blockdevice_id(
                blockdevice_id=blockdevice_id,
                size=child.getsize(),
            )
            volumes.append(volume)

        for host_directory in self._root_path.child('attached').children():
            host_name = host_directory.basename().decode('ascii')
            for child in host_directory.children():
                blockdevice_id = child.basename().decode('ascii')
                volume = _blockdevicevolume_from_blockdevice_id(
                    blockdevice_id=blockdevice_id,
                    size=child.getsize(),
                    host=host_name,
                )
                volumes.append(volume)

        return volumes

    def get_device_path(self, blockdevice_id):
        volume = self._get(blockdevice_id)
        if volume.host is None:
            raise UnattachedVolume(blockdevice_id)

        volume_path = self._attached_directory.descendant(
            [volume.host.encode("ascii"),
             volume.blockdevice_id.encode("ascii")]
        )
        # May be None if the file hasn't been used for a loop device.
        return _device_for_path(volume_path)


def _manifestation_from_volume(volume):
    """
    :param BlockDeviceVolume volume: The block device which has the
        manifestation of a dataset.
    :returns: A primary ``Manifestation`` of a ``Dataset`` with the same id as
        the supplied ``BlockDeviceVolume``.
    """
    dataset = Dataset(
        dataset_id=volume.dataset_id,
        maximum_size=volume.size,
    )
    return Manifestation(dataset=dataset, primary=True)


@implementer(IDeployer)
class BlockDeviceDeployer(PRecord):
    """
    An ``IDeployer`` that operates on ``IBlockDeviceAPI`` providers.

    :ivar unicode hostname: The IP address of the node that has this deployer.
    :ivar IBlockDeviceAPI block_device_api: The block device API that will be
        called upon to perform block device operations.
    :ivar FilePath mountroot: The directory where block devices will be
        mounted.
    :ivar _async_block_device_api: An object to override the value of the
        ``async_block_device_api`` property.  Used by tests.  Should be
        ``None`` in real-world use.
    """
    hostname = field(type=unicode, mandatory=True)
    node_uuid = field(type=UUID, mandatory=True)
    block_device_api = field(mandatory=True)
    _async_block_device_api = field(mandatory=True, initial=None)
    mountroot = field(type=FilePath, initial=FilePath(b"/flocker"))

    @property
    def async_block_device_api(self):
        """
        Get an ``IBlockDeviceAsyncAPI`` provider which can manipulate volumes
        for this deployer.

        During real operation, this is a threadpool-based wrapper around the
        ``IBlockDeviceAPI`` provider.  For testing purposes it can be
        overridden with a different object entirely (and this large amount of
        support code for this is necessary because this class is a ``PRecord``
        subclass).
        """
        if self._async_block_device_api is None:
            from twisted.internet import reactor
            return _SyncToThreadedAsyncAPIAdapter(
                _sync=self.block_device_api,
                _reactor=reactor,
                _threadpool=reactor.getThreadPool(),
            )
        return self._async_block_device_api

    def _get_system_mounts(self, volumes):
        """
        Load information about mounted filesystems related to the given
        volumes.

        :param list volumes: The ``BlockDeviceVolumes`` known to exist.  They
            may or may not be attached to this host.  Only system mounts that
            related to these volumes will be returned.

        :return: A ``dict`` mapping mount points (directories represented using
            ``FilePath``) to dataset identifiers (as ``UUID``\ s) representing
            all of the mounts on this system that were discovered and related
            to ``volumes``.
        """
        partitions = psutil.disk_partitions()
        device_to_dataset_id = {
            self.block_device_api.get_device_path(volume.blockdevice_id):
                volume.dataset_id
            for volume
            in volumes
            if volume.host == self.hostname
        }
        return {
            FilePath(partition.mountpoint):
                device_to_dataset_id[FilePath(partition.device)]
            for partition
            in partitions
            if FilePath(partition.device) in device_to_dataset_id
        }

    def discover_state(self, node_state):
        """
        Find all block devices that are currently associated with this host and
        return a ``NodeState`` containing only ``Manifestation`` instances and
        their mount paths.
        """
        api = self.block_device_api
        volumes = api.list_volumes()
        manifestations = {}
        nonmanifest = {}
        devices = {
            volume.dataset_id: api.get_device_path(volume.blockdevice_id)
            for volume
            in volumes
            if volume.host == self.hostname
        }

        for volume in volumes:
            dataset_id = unicode(volume.dataset_id)
            if volume.host == self.hostname:
                manifestations[dataset_id] = _manifestation_from_volume(
                    volume
                )
            elif volume.host is None:
                nonmanifest[dataset_id] = Dataset(dataset_id=dataset_id)

        system_mounts = self._get_system_mounts(volumes)

        paths = {}
        for manifestation in manifestations.values():
            dataset_id = manifestation.dataset.dataset_id
            mountpath = self._mountpath_for_manifestation(manifestation)

            # If the expected mount point doesn't actually have the device
            # mounted where we expected to find this manifestation, the
            # manifestation doesn't really exist here.
            properly_mounted = system_mounts.get(mountpath) == UUID(dataset_id)

            # In the future it would be nice to be able to represent
            # intermediate states (at least internally, if not exposed via the
            # API).  This makes certain IStateChange implementations easier
            # (for example, we could know something is attached and has a
            # filesystem, so we can just mount it - instead of doing something
            # about those first two state changes like trying them and handling
            # failure or doing more system inspection to try to see what's up).
            # But ... the future.

            if properly_mounted:
                paths[dataset_id] = mountpath
            else:
                del manifestations[dataset_id]
                # FLOC-1806 Populate the Dataset's size information from the
                # volume object.
                nonmanifest[dataset_id] = Dataset(dataset_id=dataset_id)

        state = (
            NodeState(
                uuid=self.node_uuid,
                hostname=self.hostname,
                manifestations=manifestations,
                paths=paths,
                devices=devices,
            ),
        )

        if nonmanifest:
            state += (NonManifestDatasets(datasets=nonmanifest),)
        return succeed(state)

    def _mountpath_for_manifestation(self, manifestation):
        """
        Calculate a ``Manifestation`` mount point.

        :param Manifestation manifestation: The manifestation of a dataset that
            will be mounted.

        :returns: A ``FilePath`` of the mount point.
        """
        return self._mountpath_for_dataset_id(manifestation.dataset_id)

    def _mountpath_for_dataset_id(self, dataset_id):
        """
        Calculate the mountpoint for a dataset.

        :param unicode dataset_id: The unique identifier of the dataset for
            which to calculate a mount point.

        :returns: A ``FilePath`` of the mount point.
        """
        return self.mountroot.child(dataset_id.encode("ascii"))

    def calculate_changes(self, configuration, cluster_state):
        this_node_config = configuration.get_node(
            self.node_uuid, hostname=self.hostname)
        configured_manifestations = this_node_config.manifestations

        configured_dataset_ids = set(
            manifestation.dataset.dataset_id
            for manifestation in configured_manifestations.values()
            # Don't create deleted datasets
            if not manifestation.dataset.deleted
        )

        local_state = cluster_state.get_node(self.node_uuid,
                                             hostname=self.hostname)
        local_dataset_ids = set(local_state.manifestations.keys())

        manifestations_to_create = set(
            configured_manifestations[dataset_id]
            for dataset_id
            in configured_dataset_ids.difference(local_dataset_ids)
            if dataset_id not in cluster_state.nonmanifest_datasets
        )

        attaches = list(self._calculate_attaches(
            local_state.devices,
            configured_manifestations,
            cluster_state.nonmanifest_datasets
        ))
        mounts = list(self._calculate_mounts(
            local_state.devices, local_state.paths, configured_manifestations,
        ))
        unmounts = list(self._calculate_unmounts(
            local_state.paths, configured_manifestations,
        ))

        # TODO prevent the configuration of unsized datasets on blockdevice
        # backends; cannot create block devices of unspecified size. FLOC-1579
        creates = list(
            CreateBlockDeviceDataset(
                dataset=manifestation.dataset,
                mountpoint=self._mountpath_for_manifestation(manifestation)
            )
            for manifestation
            in manifestations_to_create
        )

        detaches = list(self._calculate_detaches(
            local_state.devices, local_state.paths, configured_manifestations,
        ))
        deletes = self._calculate_deletes(configured_manifestations)
        resizes = list(self._calculate_resizes(
            configured_manifestations, local_state
        ))

        # TODO Prevent changes to volumes that are currently being used by
        # applications.  See the logic in P2PManifestationDeployer.  FLOC-1755.

        return in_parallel(changes=(
            unmounts + detaches +
            attaches + mounts +
            creates + deletes +
            resizes
        ))

    def _calculate_mounts(self, devices, paths, configured):
        """
        :param PMap devices: The datasets with volumes attached to this node
            and the device files at which they are available.  This is the same
            as ``NodeState.devices``.
        :param PMap paths: The paths at which datasets' filesystems are mounted
            on this node.  This is the same as ``NodeState.paths``.
        :param PMap configured: The manifestations which are configured on this
            node.  This is the same as ``NodeState.manifestations``.

        :return: A generator of ``MountBlockDevice`` instances, one for each
            dataset which exists, is attached to this node, does not have its
            filesystem mounted, and is configured to have a manifestation on
            this node.
        """
        for configured_dataset_id in configured:
            if configured_dataset_id in paths:
                # It's mounted already.
                continue
            if UUID(configured_dataset_id) in devices:
                # It's attached.
                path = self._mountpath_for_dataset_id(configured_dataset_id)
                yield MountBlockDevice(
                    dataset_id=UUID(configured_dataset_id),
                    mountpoint=path,
                )

    def _calculate_unmounts(self, paths, configured):
        """
        :param PMap paths: The paths at which datasets' filesystems are mounted
            on this node.  This is the same as ``NodeState.paths``.
        :param PMap configured: The manifestations which are configured on this
            node.  This is the same as ``NodeState.manifestations``.

        :return: A generator of ``UnmountBlockDevice`` instances, one for each
            dataset which exists, is attached to this node, has its filesystem
            mount, and is configured to not have a manifestation on this node.
        """
        for mounted_dataset_id in paths:
            if mounted_dataset_id not in configured:
                yield UnmountBlockDevice(dataset_id=UUID(mounted_dataset_id))

    def _calculate_detaches(self, devices, paths, configured):
        """
        :param PMap devices: The datasets with volumes attached to this node
            and the device files at which they are available.  This is the same
            as ``NodeState.devices``.
        :param PMap paths: The paths at which datasets' filesystems are mounted
            on this node.  This is the same as ``NodeState.paths``.
        :param PMap configured: The manifestations which are configured on this
            node.  This is the same as ``NodeState.manifestations``.

        :return: A generator of ``DetachVolume`` instances, one for each
            dataset which exists, is attached to this node, is not mounted, and
            is configured to not have a manifestation on this node.
        """
        for attached_dataset_id in devices:
            if unicode(attached_dataset_id) in configured:
                # It is supposed to be here.
                continue
            if unicode(attached_dataset_id) in paths:
                # It is mounted and needs to unmounted before it can be
                # detached.
                continue
            yield DetachVolume(dataset_id=attached_dataset_id)

    def _calculate_attaches(self, devices, configured, nonmanifest):
        """
        :param PMap devices: The datasets with volumes attached to this node
            and the device files at which they are available.  This is the same
            as ``NodeState.devices``.
        :param PMap configured: The manifestations which are configured on this
            node.  This is the same as ``NodeState.manifestations``.
        :param PMap nonmanifest: The datasets which exist in the cluster but
            are not attached to any node.

        :return: A generator of ``AttachVolume`` instances, one for each
                 dataset which exists, is unattached, and is configured to be
                 attached to this node.
        """
        for manifestation in configured.values():
            if UUID(manifestation.dataset_id) in devices:
                # It's already attached here.
                continue
            if manifestation.dataset_id in nonmanifest:
                # It exists and doesn't belong to anyone else.
                yield AttachVolume(
                    dataset_id=UUID(manifestation.dataset_id),
                    hostname=self.hostname,
                )

    def _calculate_deletes(self, configured_manifestations):
        """
        :param dict configured_manifestations: The manifestations configured
            for this node (like ``Node.manifestations``).

        :return: A ``list`` of ``DestroyBlockDeviceDataset`` instances for each
            volume that may need to be destroyed based on the given
            configuration.  A ``DestroyBlockDeviceDataset`` is returned
            even for volumes that don't exist (this is verify inefficient
            but it can be fixed later when extant volumes are included in
            cluster state - see FLOC-1616).
        """
        # This deletes everything.  Make it only delete things that exist.
        # FLOC-1756
        delete_dataset_ids = set(
            manifestation.dataset.dataset_id
            for manifestation in configured_manifestations.values()
            if manifestation.dataset.deleted
        )

        return [
            DestroyBlockDeviceDataset(dataset_id=UUID(dataset_id))
            for dataset_id
            in delete_dataset_ids
        ]

    def _calculate_resizes(self, configured_manifestations, local_state):
        """
        Determine what resizes need to be performed.

        :param dict configured_manifestations: The manifestations configured
            for this node (like ``Node.manifestations``).

        :param NodeState local_state: The current state of this node.

        :return: An iterator of ``ResizeBlockDeviceDataset`` instances for each
            volume that needs to be resized based on the given configuration
            and the actual state of volumes (ie which have a size that is
            different to the configuration)
        """
        # This won't resize nonmanifest datasets.  See FLOC-1806.
        for (dataset_id, manifestation) in local_state.manifestations.items():
            try:
                manifestation_config = configured_manifestations[dataset_id]
            except KeyError:
                continue
            dataset_config = manifestation_config.dataset
            if dataset_config.deleted:
                continue
            configured_size = dataset_config.maximum_size
            # We only inspect volume size here.  A failure could mean the
            # volume size is correct even though the filesystem size is not.
            # See FLOC-1815.
            if manifestation.dataset.maximum_size != configured_size:
                yield ResizeBlockDeviceDataset(
                    dataset_id=UUID(dataset_id),
                    size=configured_size,
                )
