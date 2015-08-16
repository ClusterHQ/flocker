# -*- test-case-name: flocker.node.agents.test.test_blockdevice -*-
# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
This module implements the parts of a block-device based dataset
convergence agent that can be re-used against many different kinds of block
devices.
"""

from uuid import UUID, uuid4
from subprocess import CalledProcessError, check_output, STDOUT
from stat import S_IRWXU, S_IRWXG, S_IRWXO
from errno import EEXIST

from bitmath import GiB

from eliot import MessageType, ActionType, Field, Logger
from eliot.serializers import identity

from zope.interface import implementer, Interface

from pyrsistent import PRecord, field
from characteristic import attributes

import psutil

from twisted.python.reflect import safe_repr
from twisted.internet.defer import succeed, fail, gatherResults
from twisted.python.filepath import FilePath
from twisted.python.components import proxyForInterface

from .. import (
    IDeployer, IStateChange, sequentially, in_parallel, run_state_change
)
from .._deploy import NotInUseDatasets

from ...control import NodeState, Manifestation, Dataset, NonManifestDatasets
from ...common import auto_threaded


# Eliot is transitioning away from the "Logger instances all over the place"
# approach.  And it's hard to put Logger instances on PRecord subclasses which
# we have a lot of.  So just use this global logger for now.
_logger = Logger()

# The size which will be assigned to datasets with an unspecified
# maximum_size.
# XXX: Make this configurable. FLOC-2679
DEFAULT_DATASET_SIZE = int(GiB(100).to_Byte().value)


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


class DatasetExists(Exception):
    """
    A ``BlockDeviceVolume`` with the requested dataset_id already exists.
    """
    def __init__(self, blockdevice):
        Exception.__init__(self, blockdevice)
        self.blockdevice = blockdevice


class FilesystemExists(Exception):
    """
    A failed attempt to create a filesystem on a block device that already has
    one.
    """
    def __init__(self, device):
        Exception.__init__(self, device)
        self.device = device


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

BLOCK_DEVICE_COMPUTE_INSTANCE_ID = Field(
    u"block_device_compute_instance_id",
    identity,
    u"An identifier for the host to which the underlying block device is "
    u"attached.",
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
     BLOCK_DEVICE_COMPUTE_INSTANCE_ID],
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

CREATE_FILESYSTEM = ActionType(
    u"agent:blockdevice:create_filesystem",
    [VOLUME, FILESYSTEM_TYPE],
    [],
    u"A block device is being initialized with a filesystem.",
)

INVALID_DEVICE_PATH_VALUE = Field(
    u"invalid_value",
    lambda value: safe_repr(value),
    u"A value returned from IBlockDeviceAPI.get_device_path which could not "
    u"possibly be correct.  This likely indicates a bug in the "
    "IBlockDeviceAPI implementation.",
)

INVALID_DEVICE_PATH = MessageType(
    u"agent:blockdevice:discover_state:invalid_device_path",
    [DATASET_ID, INVALID_DEVICE_PATH_VALUE],
    u"The device path given by the IBlockDeviceAPI implementation was "
    u"invalid.",
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
    :ivar unicode attached_to: An opaque identifier for the node to which the
        volume is attached or ``None`` if it is currently unattached.  The
        identifier is supplied by the ``IBlockDeviceAPI.compute_instance_id``
        method based on the underlying infrastructure services (for example, if
        the cluster runs on AWS, this is very likely an EC2 instance id).
    :ivar UUID dataset_id: The Flocker dataset ID associated with this volume.
    """
    blockdevice_id = field(type=unicode, mandatory=True)
    size = field(type=int, mandatory=True)
    attached_to = field(
        type=(unicode, type(None)), initial=None, mandatory=True
    )
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
            _logger, volume=self.volume, filesystem_type=self.filesystem
        )

    def run(self, deployer):
        # FLOC-1816 Make this asynchronous
        device = deployer.block_device_api.get_device_path(
            self.volume.blockdevice_id
        )
        try:
            _ensure_no_filesystem(device)
            check_output([
                b"mkfs", b"-t", self.filesystem.encode("ascii"),
                # This is ext4 specific, and ensures mke2fs doesn't ask
                # user interactively about whether they really meant to
                # format whole device rather than partition. It will be
                # removed once upstream bug is fixed. See FLOC-2085.
                b"-F",
                device.path
            ])
        except:
            return fail()
        return succeed(None)


def _ensure_no_filesystem(device):
    """
    Raises an error if there's already a filesystem on ``device``.

    :raises: ``FilesystemExists`` if there is already a filesystem on
        ``device``.
    :return: ``None``
    """
    try:
        check_output(
            [b"blkid", b"-p", b"-u", b"filesystem", device.path],
            stderr=STDOUT,
        )
    except CalledProcessError as e:
        # According to the man page:
        #   the specified token was not found, or no (specified) devices
        #   could be identified
        #
        # Experimentation shows that there is no output in the case of the
        # former, and an error printed to stderr in the case of the
        # latter.
        #
        # FLOC-2388: We're assuming an interface. We should test this
        # assumption.
        if e.returncode == 2 and not e.output:
            # There is no filesystem on this device.
            return
        raise
    raise FilesystemExists(device)


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

        # Create the directory where a device will be mounted.
        # The directory's parent's permissions will be set to only allow access
        # by owner, to limit access by other users on the node.
        try:
            self.mountpoint.makedirs()
        except OSError as e:
            if e.errno != EEXIST:
                return fail()
        self.mountpoint.parent().chmod(S_IRWXU)

        # This should be asynchronous.  FLOC-1797
        check_output([b"mount", device.path, self.mountpoint.path])

        # Remove lost+found to ensure filesystems always start out empty.
        # Mounted filesystem is also made world
        # writeable/readable/executable since we can't predict what user a
        # container will run as.  We make sure we change mounted
        # filesystem's root directory permissions, so we only do this
        # after the filesystem is mounted.  If other files exist we don't
        # bother with either change, since at that point user has modified
        # the volume and we don't want to undo their changes by mistake
        # (e.g. postgres doesn't like world-writeable directories once
        # it's initialized).

        # A better way is described in
        # https://clusterhq.atlassian.net/browse/FLOC-2074
        lostfound = self.mountpoint.child(b"lost+found")
        if self.mountpoint.children() == [lostfound]:
            lostfound.remove()
            self.mountpoint.chmod(S_IRWXU | S_IRWXG | S_IRWXO)
            self.mountpoint.restat()

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
    Attach an unattached volume to this node (the node of the deployer it is
    run with).

    :ivar UUID dataset_id: The unique identifier of the dataset associated with
        the volume to attach.
    """
    dataset_id = field(type=UUID, mandatory=True)

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
        getting_id = api.compute_instance_id()

        d = gatherResults([listing, getting_id])

        def found((volume, compute_instance_id)):
            if volume is None:
                # It was not actually found.
                raise DatasetWithoutVolume(dataset_id=self.dataset_id)
            ATTACH_VOLUME_DETAILS(volume=volume).write(_logger)
            return api.attach_volume(
                volume.blockdevice_id,
                attach_to=compute_instance_id,
            )
        attaching = d.addCallback(found)
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
        # FLOC-1818 Make this asynchronous
        deployer.block_device_api.destroy_volume(self.volume.blockdevice_id)
        return succeed(None)


def allocated_size(allocation_unit, requested_size):
    """
    Round ``requested_size`` up to the nearest ``allocation_unit``.

    :param int allocation_unit: The interval in ``bytes`` to which
        ``requested_size`` will be rounded up.
    :param int requested_size: The size in ``bytes`` that is required.
    :return: The ``allocated_size`` in ``bytes``.
    """
    allocation_unit = int(allocation_unit)
    requested_size = int(requested_size)

    previous_interval_size = (
        (requested_size // allocation_unit)
        * allocation_unit
    )
    if previous_interval_size < requested_size:
        return previous_interval_size + allocation_unit
    else:
        return requested_size


def check_allocatable_size(allocation_unit, requested_size):
    """
    :param int allocation_unit: The interval in ``bytes`` to which
        ``requested_size`` will be rounded up.
    :param int requested_size: The size in ``bytes`` that is required.
    :raises: ``ValueError`` unless ``requested_size`` is exactly
        divisible by ``allocation_unit``.
    """
    actual_size = allocated_size(allocation_unit, requested_size)
    if requested_size != actual_size:
        raise ValueError(
            'Requested size {!r} is not divisible by {!r}'.format(
                requested_size, allocation_unit
            )
        )


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

        :returns: An already fired ``Deferred`` with result ``None`` or a
            failed ``Deferred`` with a ``DatasetExists`` exception if a
            blockdevice with the required dataset_id already exists.
        """
        api = deployer.block_device_api
        try:
            check_for_existing_dataset(api, UUID(hex=self.dataset.dataset_id))
        except:
            return fail()

        volume = api.create_volume(
            dataset_id=UUID(self.dataset.dataset_id),
            size=allocated_size(
                allocation_unit=api.allocation_unit(),
                requested_size=self.dataset.maximum_size,
            ),
        )

        # This duplicates AttachVolume now.
        volume = api.attach_volume(
            volume.blockdevice_id,
            attach_to=api.compute_instance_id(),
        )
        device = api.get_device_path(volume.blockdevice_id)

        create = CreateFilesystem(volume=volume, filesystem=u"ext4")
        d = run_state_change(create, deployer)

        mount = MountBlockDevice(dataset_id=UUID(hex=self.dataset.dataset_id),
                                 mountpoint=self.mountpoint)
        d.addCallback(lambda _: run_state_change(mount, deployer))

        def passthrough(result):
            BLOCK_DEVICE_DATASET_CREATED(
                block_device_path=device,
                block_device_id=volume.blockdevice_id,
                dataset_id=volume.dataset_id,
                block_device_size=volume.size,
                block_device_compute_instance_id=volume.attached_to,
            ).write(_logger)
            return result
        d.addCallback(passthrough)
        return d


class IBlockDeviceAsyncAPI(Interface):
    """
    Common operations provided by all block device backends, exposed via
    asynchronous methods.
    """
    def allocation_unit():
        """
        See ``IBlockDeviceAPI.allocation_unit``.

        :returns: A ``Deferred`` that fires with ``int`` size of the
            allocation_unit.
        """

    def compute_instance_id():
        """
        See ``IBlockDeviceAPI.compute_instance_id``.

        :returns: A ``Deferred`` that fires with ``unicode`` of a
            provider-specific node identifier which identifies the node where
            the method is run.
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

    def attach_volume(blockdevice_id, attach_to):
        """
        See ``IBlockDeviceAPI.attach_volume``.

        :returns: A ``Deferred`` that fires with a ``BlockDeviceVolume`` with a
            ``attached_to`` attribute set to ``attach_to``.
        """

    def detach_volume(blockdevice_id):
        """
        See ``BlockDeviceAPI.detach_volume``.

        :returns: A ``Deferred`` that fires when the volume has been detached.
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
    def allocation_unit():
        """
        The size, in bytes up to which ``IDeployer`` will round volume
        sizes before calling ``IBlockDeviceAPI.create_volume``.

        :rtype: ``int``
        """

    def compute_instance_id():
        """
        Get an identifier for this node.

        This will be compared against ``BlockDeviceVolume.attached_to``
        to determine which volumes are locally attached and it will be used
        with ``attach_volume`` to locally attach volumes.

        :returns: A ``unicode`` object giving a provider-specific node
            identifier which identifies the node where the method is run.
        """

    def create_volume(dataset_id, size):
        """
        Create a new volume.

        When called by ``IDeployer``, the supplied size will be
        rounded up to the nearest
        ``IBlockDeviceAPI.allocation_unit()``

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

    def attach_volume(blockdevice_id, attach_to):
        """
        Attach ``blockdevice_id`` to the node indicated by ``attach_to``.

        :param unicode blockdevice_id: The unique identifier for the block
            device being attached.
        :param unicode attach_to: An identifier like the one returned by the
            ``compute_instance_id`` method indicating the node to which to
            attach the volume.

        :raises UnknownVolume: If the supplied ``blockdevice_id`` does not
            exist.
        :raises AlreadyAttachedVolume: If the supplied ``blockdevice_id`` is
            already attached.

        :returns: A ``BlockDeviceVolume`` with a ``attached_to`` attribute set
            to ``attach_to``.
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


def _blockdevicevolume_from_dataset_id(dataset_id, size,
                                       attached_to=None):
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
        size=size, attached_to=attached_to,
        dataset_id=dataset_id, blockdevice_id=u"block-{0}".format(dataset_id),
    )


def _blockdevicevolume_from_blockdevice_id(blockdevice_id, size,
                                           attached_to=None):
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
        size=size, attached_to=attached_to,
        dataset_id=dataset_id,
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


def check_for_existing_dataset(api, dataset_id):
    """
    :param IBlockDeviceAPI api: The ``api`` for listing the existing volumes.
    :param UUID dataset_id: The dataset_id to check for.

    :raises: ``DatasetExists`` if there is already a ``BlockDeviceVolume`` with
        the supplied ``dataset_id``.
    """
    volumes = api.list_volumes()
    for volume in volumes:
        if volume.dataset_id == dataset_id:
            raise DatasetExists(volume)


def get_blockdevice_volume(api, blockdevice_id):
    """
    Find a ``BlockDeviceVolume`` matching the given identifier.

    :param unicode blockdevice_id: The backend identifier of the volume to
        find.

    :raise UnknownVolume: If no volume with a matching identifier can be
        found.

    :return: The ``BlockDeviceVolume`` that matches.
    """
    for volume in api.list_volumes():
        if volume.blockdevice_id == blockdevice_id:
            return volume
    raise UnknownVolume(blockdevice_id)


DEFAULT_LOOPBACK_PATH = '/var/lib/flocker/loopback'


def _backing_file_name(volume):
    """
    :param BlockDeviceVolume: The volume for which to generate a
        loopback file name.
    :returns: A filename containing the encoded
        ``volume.blockdevic_id`` and ``volume.size``.
    """
    return volume.blockdevice_id.encode('ascii') + '_' + bytes(volume.size)


@implementer(IBlockDeviceAPI)
class LoopbackBlockDeviceAPI(object):
    """
    A simulated ``IBlockDeviceAPI`` which creates loopback devices backed by
    files located beneath the supplied ``root_path``.
    """
    _attached_directory_name = 'attached'
    _unattached_directory_name = 'unattached'

    def __init__(self, root_path, compute_instance_id, allocation_unit=None):
        """
        :param FilePath root_path: The path beneath which all loopback backing
            files and their organising directories will be created.
        :param unicode compute_instance_id: An identifier to use to identify
            "this" node amongst a collection of users of the same loopback
            storage area.  Instances which are meant to behave as though they
            are running on a separate node from each other should have
            different ``compute_instance_id``.
        :param int allocation_unit: The size (in bytes) that will be
            reported by ``allocation_unit``. Default is ``1``.
        """
        self._root_path = root_path
        self._compute_instance_id = compute_instance_id
        if allocation_unit is None:
            allocation_unit = 1
        self._allocation_unit = allocation_unit

    @classmethod
    def from_path(
            cls, root_path=DEFAULT_LOOPBACK_PATH, compute_instance_id=None,
            allocation_unit=None):
        """
        :param bytes root_path: The path to a directory in which loop back
            backing files will be created.  The directory is created if it does
            not already exist.
        :param compute_instance_id: See ``__init__``.  Additionally, if not
            given, a new random id will be generated.
        :param int allocation_unit: The size (in bytes) that will be
            reported by ``allocation_unit``. Default is ``1``.

        :returns: A ``LoopbackBlockDeviceAPI`` with the supplied ``root_path``.
        """
        if compute_instance_id is None:
            # If no compute_instance_id provided, invent one.
            compute_instance_id = unicode(uuid4())
        api = cls(
            root_path=FilePath(root_path),
            compute_instance_id=compute_instance_id,
            allocation_unit=allocation_unit,
        )
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

    def allocation_unit(self):
        return self._allocation_unit

    def compute_instance_id(self):
        return self._compute_instance_id

    def _parse_backing_file_name(self, filename):
        """
        :param unicode filename: The backing file name to decode.
        :returns: A 2-tuple of ``unicode`` blockdevice_id, and ``int``
            size.
        """
        blockdevice_id, size = filename.rsplit('_', 1)
        size = int(size)
        return blockdevice_id, size

    def create_volume(self, dataset_id, size):
        """
        Create a "sparse" file of some size and put it in the ``unattached``
        directory.

        See ``IBlockDeviceAPI.create_volume`` for parameter and return type
        documentation.
        """
        check_allocatable_size(self.allocation_unit(), size)
        volume = _blockdevicevolume_from_dataset_id(
            size=size, dataset_id=dataset_id,
        )
        with self._unattached_directory.child(
            _backing_file_name(volume)
        ).open('wb') as f:
            f.truncate(size)
        return volume

    def destroy_volume(self, blockdevice_id):
        """
        Destroy the storage for the given unattached volume.
        """
        volume = get_blockdevice_volume(self, blockdevice_id)
        volume_path = self._unattached_directory.child(
            _backing_file_name(volume)
        )
        volume_path.remove()

    def _allocate_device(self, backing_file_path):
        """
        Create a loopback device backed by the file at the given path.

        :param FilePath backing_file_path: The path of the file that is the
            backing store for the new device.
        """
        # The --find option allocates the next available /dev/loopX device
        # name to the device.
        check_output(["losetup", "--find", backing_file_path.path])

    def attach_volume(self, blockdevice_id, attach_to):
        """
        Move an existing ``unattached`` file into a per-node directory and
        create a loopback device backed by that file.

        Note: Although `mkfs` can format files directly and `mount` can mount
        files directly (with the `-o loop` option), we want to simulate a real
        block device which will be allocated a real block device file on the
        node to which it is attached. This allows the consumer of this API to
        perform formatting and mount operations exactly the same as for a real
        block device.

        See ``IBlockDeviceAPI.attach_volume`` for parameter and return type
        documentation.
        """
        volume = get_blockdevice_volume(self, blockdevice_id)
        filename = _backing_file_name(volume)
        if volume.attached_to is None:
            old_path = self._unattached_directory.child(filename)
            host_directory = self._attached_directory.child(
                attach_to.encode("ascii"),
            )
            try:
                host_directory.makedirs()
            except OSError:
                pass
            new_path = host_directory.child(filename)
            old_path.moveTo(new_path)
            self._allocate_device(new_path)
            attached_volume = volume.set(attached_to=attach_to)
            return attached_volume

        raise AlreadyAttachedVolume(blockdevice_id)

    def detach_volume(self, blockdevice_id):
        """
        Move an existing file from a per-host directory into the ``unattached``
        directory and release the loopback device backed by that file.
        """
        volume = get_blockdevice_volume(self, blockdevice_id)
        if volume.attached_to is None:
            raise UnattachedVolume(blockdevice_id)

        # ``losetup --detach`` only if the file was used for a loop device.
        if self.get_device_path(blockdevice_id) is not None:
            check_output([
                b"losetup", b"--detach",
                self.get_device_path(blockdevice_id).path
            ])

        filename = _backing_file_name(volume)
        volume_path = self._attached_directory.descendant([
            volume.attached_to.encode("ascii"),
            filename,
        ])
        new_path = self._unattached_directory.child(
            filename
        )
        volume_path.moveTo(new_path)

    def list_volumes(self):
        """
        Return ``BlockDeviceVolume`` instances for all the files in the
        ``unattached`` directory and all per-host directories.

        See ``IBlockDeviceAPI.list_volumes`` for parameter and return type
        documentation.
        """
        volumes = []
        for child in self._root_path.child('unattached').children():
            blockdevice_id, size = self._parse_backing_file_name(
                child.basename().decode('ascii')
            )
            volume = _blockdevicevolume_from_blockdevice_id(
                blockdevice_id=blockdevice_id,
                size=size,
            )
            volumes.append(volume)

        for host_directory in self._root_path.child('attached').children():
            compute_instance_id = host_directory.basename().decode('ascii')
            for child in host_directory.children():
                blockdevice_id, size = self._parse_backing_file_name(
                    child.basename().decode('ascii')
                )
                volume = _blockdevicevolume_from_blockdevice_id(
                    blockdevice_id=blockdevice_id,
                    size=size,
                    attached_to=compute_instance_id,
                )
                volumes.append(volume)

        return volumes

    def get_device_path(self, blockdevice_id):
        volume = get_blockdevice_volume(self, blockdevice_id)
        if volume.attached_to is None:
            raise UnattachedVolume(blockdevice_id)

        volume_path = self._attached_directory.descendant(
            [volume.attached_to.encode("ascii"),
             _backing_file_name(volume)]
        )
        # May be None if the file hasn't been used for a loop device.
        path = _device_for_path(volume_path)
        if path is None:
            # It was supposed to be attached (the backing file was stored in a
            # child of the "attached" directory, so someone had called
            # `attach_volume` and not `detach_volume` for it) but it has no
            # loopback device.  So its actual state is only partially attached.
            # Fix it so it's all-the-way attached.  This might happen because
            # the node OS was rebooted, for example.
            self._allocate_device(volume_path)
            path = _device_for_path(volume_path)
        return path


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

    def _get_system_mounts(self, volumes, compute_instance_id):
        """
        Load information about mounted filesystems related to the given
        volumes.

        :param list volumes: The ``BlockDeviceVolumes`` known to exist.  They
            may or may not be attached to this host.  Only system mounts that
            related to these volumes will be returned.

        :param unicode compute_instance_id: This node's identifier.

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
            if volume.attached_to == compute_instance_id
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
        # FLOC-1819 Make this asynchronous
        api = self.block_device_api
        compute_instance_id = api.compute_instance_id()
        volumes = api.list_volumes()
        manifestations = {}
        nonmanifest = {}

        def is_existing_block_device(dataset_id, path):
            if isinstance(path, FilePath) and path.isBlockDevice():
                return True
            INVALID_DEVICE_PATH(
                dataset_id=dataset_id, invalid_value=path
            ).write(_logger)
            return False

        # Find the devices for any manifestations on this node.  Build up a
        # collection of non-manifest dataset as well.  Anything that looks like
        # it could be a manifestation on this node but that has some kind of
        # inconsistent state is left out altogether.
        devices = {}
        for volume in volumes:
            dataset_id = volume.dataset_id
            u_dataset_id = unicode(dataset_id)
            if volume.attached_to == compute_instance_id:
                device_path = api.get_device_path(volume.blockdevice_id)
                if is_existing_block_device(dataset_id, device_path):
                    devices[dataset_id] = device_path
                    manifestations[u_dataset_id] = _manifestation_from_volume(
                        volume
                    )
            elif volume.attached_to is None:
                # XXX: Looks like we don't attempt to report the size
                # of non-manifest datasets.
                # Why not? The size is available from the volume.
                # https://clusterhq.atlassian.net/browse/FLOC-1983
                nonmanifest[u_dataset_id] = Dataset(dataset_id=dataset_id)

        system_mounts = self._get_system_mounts(volumes, compute_instance_id)

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
                # XXX: Here again, it we mark the dataset as
                # `nonmanifest`` unless it's actually mounted but we
                # don't attempt to report the size.
                # Why not? The size is available from the volume.
                # It seems like state reporting bug and separate from
                # (although blocking) FLOC-1806.
                # https://clusterhq.atlassian.net/browse/FLOC-1983
                nonmanifest[dataset_id] = Dataset(dataset_id=dataset_id)

        state = (
            NodeState(
                uuid=self.node_uuid,
                hostname=self.hostname,
                manifestations=manifestations,
                paths=paths,
                devices=devices,
                # Discovering these is ApplicationNodeDeployer's job, we
                # don't anything about these:
                applications=None,
                used_ports=None,
            ),
            NonManifestDatasets(datasets=nonmanifest),
        )

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
        local_state = cluster_state.get_node(self.node_uuid,
                                             hostname=self.hostname)

        # We need to know applications (for now) to see if we should delay
        # deletion or handoffs. Eventually this will rely on leases instead.
        # https://clusterhq.atlassian.net/browse/FLOC-1425.
        if local_state.applications is None:
            return in_parallel(changes=[])

        not_in_use = NotInUseDatasets(local_state)

        configured_manifestations = this_node_config.manifestations

        configured_dataset_ids = set(
            manifestation.dataset.dataset_id
            for manifestation in configured_manifestations.values()
            # Don't create deleted datasets
            if not manifestation.dataset.deleted
        )

        local_dataset_ids = set(local_state.manifestations.keys())

        manifestations_to_create = set()
        all_dataset_ids = list(
            dataset.dataset_id
            for dataset, node
            in cluster_state.all_datasets()
        )
        for dataset_id in configured_dataset_ids.difference(local_dataset_ids):
            if dataset_id in all_dataset_ids:
                continue
            else:
                manifestation = configured_manifestations[dataset_id]
                # XXX: Make this configurable. FLOC-2679
                if manifestation.dataset.maximum_size is None:
                    manifestation = manifestation.transform(
                        ['dataset', 'maximum_size'],
                        DEFAULT_DATASET_SIZE
                    )
                manifestations_to_create.add(manifestation)

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

        # XXX prevent the configuration of unsized datasets on blockdevice
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
        deletes = self._calculate_deletes(
            local_state, configured_manifestations)

        # FLOC-1484 Support resize for block storage backends. See also
        # FLOC-1875.

        return in_parallel(changes=(
            not_in_use(unmounts) + detaches +
            attaches + mounts +
            creates + not_in_use(deletes)
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
                )

    def _calculate_deletes(self, local_state, configured_manifestations):
        """
        :param NodeState: The local state discovered immediately prior to
            calculation.

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
            if dataset_id in local_state.manifestations
        ]


class ProcessLifetimeCache(proxyForInterface(IBlockDeviceAPI, "_api")):
    """
    A transparent caching layer around an ``IBlockDeviceAPI`` instance,
    intended to exist for the lifetime of the process.

    :ivar _api: Wrapped ``IBlockDeviceAPI`` provider.
    :ivar _instance_id: Cached result of ``compute_instance_id``.
    :ivar _device_paths: Mapping from blockdevice ids to cached device path.
    """
    def __init__(self, api):
        self._api = api
        self._instance_id = None
        self._device_paths = {}

    def compute_instance_id(self):
        """
        Always return initial result since this shouldn't change until a
        reboot.
        """
        if self._instance_id is None:
            self._instance_id = self._api.compute_instance_id()
        return self._instance_id

    def get_device_path(self, blockdevice_id):
        """
        Load the device path from a cache if possible.
        """
        if blockdevice_id not in self._device_paths:
            self._device_paths[blockdevice_id] = self._api.get_device_path(
                blockdevice_id)
        return self._device_paths[blockdevice_id]

    def detach_volume(self, blockdevice_id):
        """
        Clear the cached device path, if it was cached.
        """
        try:
            del self._device_paths[blockdevice_id]
        except KeyError:
            pass
        return self._api.detach_volume(blockdevice_id)
