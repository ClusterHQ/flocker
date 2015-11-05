# -*- test-case-name: flocker.node.agents.test.test_blockdevice -*-
# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
This module implements the parts of a block-device based dataset
convergence agent that can be re-used against many different kinds of block
devices.
"""

from uuid import UUID
from subprocess import CalledProcessError, check_output, STDOUT
from stat import S_IRWXU, S_IRWXG, S_IRWXO
from errno import EEXIST
from datetime import timedelta

from bitmath import GiB

from eliot import MessageType, ActionType, Field, Logger
from eliot.serializers import identity

from zope.interface import implementer, Interface

from pyrsistent import PRecord, PClass, field

import psutil

from twisted.python.reflect import safe_repr
from twisted.internet.defer import succeed, fail
from twisted.python.filepath import FilePath
from twisted.python.components import proxyForInterface
from twisted.python.constants import Values, ValueConstant

from .. import (
    IDeployer, ILocalState, IStateChange, sequentially, in_parallel,
    run_state_change
)
from .._deploy import NotInUseDatasets

from ...control import NodeState, Manifestation, Dataset, NonManifestDatasets
from ...control._model import pvector_field
from ...common import auto_threaded


# Eliot is transitioning away from the "Logger instances all over the place"
# approach.  And it's hard to put Logger instances on PRecord subclasses which
# we have a lot of.  So just use this global logger for now.
_logger = Logger()

# The size which will be assigned to datasets with an unspecified
# maximum_size.
# XXX: Make this configurable. FLOC-2679
DEFAULT_DATASET_SIZE = int(GiB(100).to_Byte().value)

# The metadata key for flocker profiles.
PROFILE_METADATA_KEY = u"clusterhq:flocker:profile"


class VolumeException(Exception):
    """
    A base class for exceptions raised by  ``IBlockDeviceAPI`` operations.

    :param unicode blockdevice_id: The unique identifier of the
        ``IBlockDeviceAPI``-managed volume.
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


class UnknownInstanceID(Exception):
    """
    Could not compute instance ID for block device.
    """
    def __init__(self, blockdevice):
        Exception.__init__(
            self,
            'Could not find valid instance ID for {}'.format(blockdevice))
        self.blockdevice = blockdevice


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

PROFILE_NAME = Field.forTypes(
    u"profile_name",
    [unicode],
    u"The name of a profile for a volume."
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
    [BLOCK_DEVICE_ID, BLOCK_DEVICE_PATH],
    u"The device file for a block-device-backed dataset has been discovered."
)

MOUNT_BLOCK_DEVICE = ActionType(
    u"agent:blockdevice:mount",
    [DATASET_ID, BLOCK_DEVICE_ID],
    [],
    u"A block-device-backed dataset is being mounted.",
)

MOUNT_BLOCK_DEVICE_DETAILS = MessageType(
    u"agent:blockdevice:mount:details",
    [BLOCK_DEVICE_PATH],
    u"The device file for a block-device-backed dataset has been discovered."
)

ATTACH_VOLUME = ActionType(
    u"agent:blockdevice:attach_volume",
    [DATASET_ID, BLOCK_DEVICE_ID],
    [],
    u"The volume for a block-device-backed dataset is being attached."
)

DETACH_VOLUME = ActionType(
    u"agent:blockdevice:detach_volume",
    [DATASET_ID, BLOCK_DEVICE_ID],
    [],
    u"The volume for a block-device-backed dataset is being detached."
)

DESTROY_VOLUME = ActionType(
    u"agent:blockdevice:destroy_volume",
    [BLOCK_DEVICE_ID],
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

CREATE_VOLUME_PROFILE_DROPPED = MessageType(
    u"agent:blockdevice:profiles:create_volume_with_profiles:profile_dropped",
    [DATASET_ID, PROFILE_NAME],
    u"The profile of a volume was dropped during creation because the backend "
    u"does not support profiles. Use a backend that provides "
    u"IProfiledBlockDeviceAPI to get profile support."
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


class BlockDeviceVolume(PClass):
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
    :ivar unicode blockdevice_id: The unique identifier of the
        ``IBlockDeviceAPI``-managed volume to be destroyed.
    """
    dataset_id = field(type=UUID, mandatory=True)
    blockdevice_id = field(type=unicode, mandatory=True)

    # This can be replaced with a regular attribute when the `_logger` argument
    # is no longer required by Eliot.
    @property
    def eliot_action(self):
        return DESTROY_BLOCK_DEVICE_DATASET(
            _logger, dataset_id=self.dataset_id
        )

    def run(self, deployer):
        return run_state_change(
            sequentially(
                changes=[
                    UnmountBlockDevice(dataset_id=self.dataset_id,
                                       blockdevice_id=self.blockdevice_id),
                    DetachVolume(dataset_id=self.dataset_id,
                                 blockdevice_id=self.blockdevice_id),
                    DestroyVolume(blockdevice_id=self.blockdevice_id),
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
    :ivar unicode blockdevice_id: The unique identifier of the
        ``IBlockDeviceAPI``-managed volume to be mounted.
    :ivar FilePath mountpoint: The filesystem location at which to mount the
        volume's filesystem.  If this does not exist, it is created.
    """
    dataset_id = field(type=UUID, mandatory=True)
    blockdevice_id = field(type=unicode, mandatory=True)
    mountpoint = field(type=FilePath, mandatory=True)

    @property
    def eliot_action(self):
        return MOUNT_BLOCK_DEVICE(_logger, dataset_id=self.dataset_id,
                                  block_device_id=self.blockdevice_id)

    def run(self, deployer):
        """
        Run the system ``mount`` tool to mount this change's volume's block
        device.  The volume must be attached to this node.
        """
        api = deployer.block_device_api
        device = api.get_device_path(self.blockdevice_id)
        MOUNT_BLOCK_DEVICE_DETAILS(block_device_path=device).write(_logger)

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
    :ivar unicode blockdevice_id: The unique identifier of the mounted
        ``IBlockDeviceAPI``-managed volume to be unmounted.
    """
    dataset_id = field(type=UUID, mandatory=True)
    blockdevice_id = field(type=unicode, mandatory=True)

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
        deferred_device_path = api.get_device_path(self.blockdevice_id)

        def got_device(device):
            UNMOUNT_BLOCK_DEVICE_DETAILS(
                block_device_id=self.blockdevice_id,
                block_device_path=device
            ).write(_logger)
            # This should be asynchronous. FLOC-1797
            check_output([b"umount", device.path])
        deferred_device_path.addCallback(got_device)
        return deferred_device_path


@implementer(IStateChange)
class AttachVolume(PRecord):
    """
    Attach an unattached volume to this node (the node of the deployer it is
    run with).

    :ivar UUID dataset_id: The unique identifier of the dataset associated with
        the volume to attach.
    :ivar unicode blockdevice_id: The unique identifier of the
        ``IBlockDeviceAPI``-managed volume to be attached.
    """
    dataset_id = field(type=UUID, mandatory=True)
    blockdevice_id = field(type=unicode, mandatory=True)

    @property
    def eliot_action(self):
        return ATTACH_VOLUME(_logger, dataset_id=self.dataset_id,
                             blockdevice_id=self.blockdevice_id)

    def run(self, deployer):
        """
        Use the deployer's ``IBlockDeviceAPI`` to attach the volume.
        """
        api = deployer.async_block_device_api
        getting_id = api.compute_instance_id()

        def got_compute_id(compute_instance_id):
            return api.attach_volume(
                self.blockdevice_id,
                attach_to=compute_instance_id,
            )
        attaching = getting_id.addCallback(got_compute_id)
        return attaching


@implementer(IStateChange)
class DetachVolume(PRecord):
    """
    Detach a volume from the node it is currently attached to.

    :ivar UUID dataset_id: The unique identifier of the dataset associated with
        the volume to detach.
    :ivar unicode blockdevice_id: The unique identifier of the
        ``IBlockDeviceAPI``-managed volume to be detached.
    """
    dataset_id = field(type=UUID, mandatory=True)
    blockdevice_id = field(type=unicode, mandatory=True)

    @property
    def eliot_action(self):
        return DETACH_VOLUME(_logger, dataset_id=self.dataset_id,
                             block_device_id=self.blockdevice_id)

    def run(self, deployer):
        """
        Use the deployer's ``IBlockDeviceAPI`` to detach the volume.
        """
        api = deployer.async_block_device_api
        return api.detach_volume(self.blockdevice_id)


@implementer(IStateChange)
class DestroyVolume(PRecord):
    """
    Destroy the storage (and therefore contents) of a volume.

    :ivar unicode blockdevice_id: The unique identifier of the
        ``IBlockDeviceAPI``-managed volume to be destroyed.
    """
    blockdevice_id = field(type=unicode, mandatory=True)

    @property
    def eliot_action(self):
        return DESTROY_VOLUME(_logger, block_device_id=self.blockdevice_id)

    def run(self, deployer):
        """
        Use the deployer's ``IBlockDeviceAPI`` to destroy the volume.
        """
        api = deployer.async_block_device_api
        return api.destroy_volume(self.blockdevice_id)


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


# Get rid of this in favor of calculating each individual operation in
# BlockDeviceDeployer.calculate_changes. Also consider splitting the
# CreateVolume portion of the IStateChange into 2 IStateChanges, one for
# creating a volume with a profile, and one for creating a volume without a
# profile. FLOC-1771
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

    def _create_volume(self, deployer):
        """
        Create the volume using the backend API. This method will create the
        volume with a profile if the metadata on the volume suggests that we
        should

        :param deployer: The deployer to use to create the volume.

        :returns: The created ``BlockDeviceVolume``.
        """
        api = deployer.block_device_api
        profile_name = self.dataset.metadata.get(PROFILE_METADATA_KEY)
        dataset_id = UUID(self.dataset.dataset_id)
        size = allocated_size(allocation_unit=api.allocation_unit(),
                              requested_size=self.dataset.maximum_size)
        if profile_name:
            return (
                deployer.profiled_blockdevice_api.create_volume_with_profile(
                    dataset_id=dataset_id,
                    size=size,
                    profile_name=profile_name
                )
            )
        else:
            return api.create_volume(dataset_id=dataset_id, size=size)

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

        volume = self._create_volume(deployer)

        # This duplicates AttachVolume now.
        volume = api.attach_volume(
            volume.blockdevice_id,
            attach_to=api.compute_instance_id(),
        )
        device = api.get_device_path(volume.blockdevice_id)

        create = CreateFilesystem(volume=volume, filesystem=u"ext4")
        d = run_state_change(create, deployer)

        mount = MountBlockDevice(dataset_id=volume.dataset_id,
                                 blockdevice_id=volume.blockdevice_id,
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
            the method is run, or fails with ``UnknownInstanceID`` if we cannot
            determine the identifier.
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

        :raise UnknownInstanceID: If we cannot determine the identifier of the
            node.
        :returns: A ``unicode`` object giving a provider-specific node
            identifier which identifies the node where the method is run.
        """

    def create_volume(dataset_id, size):
        """
        Create a new volume.

        When called by ``IDeployer``, the supplied size will be
        rounded up to the nearest
        ``IBlockDeviceAPI.allocation_unit()``

        If the backend supports human-facing volumes names (i.e. names
        that show up in management UIs) then it is recommended that the
        newly created volume should be given a name that contains the
        dataset_id in order to ease debugging. Some implementations may
        choose not to do so or may not be able to do so.

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


class MandatoryProfiles(Values):
    """
    Mandatory Storage Profiles to be implemented by ``IProfiledBlockDeviceAPI``
    implementers.  These will have driver-specific meaning, with the following
    desired meaning:

    :ivar GOLD: The profile for fast storage.
    :ivar SILVER: The profile for intermediate/default storage.
    :ivar BRONZE: The profile for cheap storage.
    :ivar DEFAULT: The default profile if none is specified.
    """
    GOLD = ValueConstant(u'gold')
    SILVER = ValueConstant(u'silver')
    BRONZE = ValueConstant(u'bronze')
    DEFAULT = ValueConstant(BRONZE.value)


class IProfiledBlockDeviceAPI(Interface):
    """
    An interface for drivers that are capable of creating volumes with a
    specific profile.
    """

    def create_volume_with_profile(dataset_id, size, profile_name):
        """
        Create a new volume with the specified profile.

        When called by ``IDeployer``, the supplied size will be
        rounded up to the nearest ``IBlockDeviceAPI.allocation_unit()``.


        :param UUID dataset_id: The Flocker dataset ID of the dataset on this
            volume.
        :param int size: The size of the new volume in bytes.
        :param unicode profile_name: The name of the storage profile for this
            volume.

        :returns: A ``BlockDeviceVolume`` of the newly created volume.
        """


@implementer(IProfiledBlockDeviceAPI)
class ProfiledBlockDeviceAPIAdapter(PClass):
    """
    Adapter class to create ``IProfiledBlockDeviceAPI`` providers for
    ``IBlockDeviceAPI`` implementations that do not implement
    ``IProfiledBlockDeviceAPI``

    :ivar _blockdevice_api: The ``IBlockDeviceAPI`` provider to back the
        volume creation.
    """
    _blockdevice_api = field(
        mandatory=True,
        invariant=lambda i: (IBlockDeviceAPI.providedBy(i),
                             '_blockdevice_api must provide IBlockDeviceAPI'))

    def create_volume_with_profile(self, dataset_id, size, profile_name):
        """
        Reverts to constructing a volume with no profile. To be used with
        backends that do not implement ``IProfiledBlockDeviceAPI``, but do
        implement ``IBlockDeviceAPI``.
        """
        CREATE_VOLUME_PROFILE_DROPPED(dataset_id=dataset_id,
                                      profile_name=profile_name).write()
        return self._blockdevice_api.create_volume(dataset_id=dataset_id,
                                                   size=size)


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


@implementer(ILocalState)
class BlockDeviceDeployerLocalState(PClass):
    """
    An ``ILocalState`` implementation for the ``BlockDeviceDeployer``.

    :ivar NodeState node_state: The current ``NodeState`` for this node.

    :ivar NonManifestDatasets nonmanifest_datasets: The current
        ``NonManifestDatasets`` that this node is aware of but are not attached
        to any node.

    :ivar volumes: A ``PVector`` of ``BlockDeviceVolume`` instances for all
        volumes in the cluster that this node is aware of.
    """
    node_state = field(type=NodeState, mandatory=True)
    nonmanifest_datasets = field(type=NonManifestDatasets, mandatory=True)
    volumes = pvector_field(BlockDeviceVolume)

    def shared_state_changes(self):
        """
        Returns the NodeState and the NonManifestDatasets of the local state.
        These are the only parts of the state that need to be sent to the
        control service.
        """
        return (self.node_state, self.nonmanifest_datasets)


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
    poll_interval = timedelta(seconds=60.0)

    @property
    def profiled_blockdevice_api(self):
        """
        Get an ``IProfiledBlockDeviceAPI`` provider which can create volumes
        configured based on pre-defined profiles.
        """
        if IProfiledBlockDeviceAPI.providedBy(self.block_device_api):
            return self.block_device_api
        return ProfiledBlockDeviceAPIAdapter(
            _blockdevice_api=self.block_device_api
        )

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

        local_state = BlockDeviceDeployerLocalState(
            node_state=NodeState(
                uuid=self.node_uuid,
                hostname=self.hostname,
                manifestations=manifestations,
                paths=paths,
                devices=devices,
                # Discovering these is ApplicationNodeDeployer's job, we
                # don't know anything about these:
                applications=None,
            ),
            nonmanifest_datasets=NonManifestDatasets(datasets=nonmanifest),
            volumes=volumes,
        )

        return succeed(local_state)

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

    def calculate_changes(self, configuration, cluster_state, local_state):
        this_node_config = configuration.get_node(
            self.node_uuid, hostname=self.hostname)
        local_node_state = cluster_state.get_node(self.node_uuid,
                                                  hostname=self.hostname)

        # We need to know applications (for now) to see if we should delay
        # deletion or handoffs. Eventually this will rely on leases instead.
        # https://clusterhq.atlassian.net/browse/FLOC-1425.
        if local_node_state.applications is None:
            return in_parallel(changes=[])

        not_in_use = NotInUseDatasets(local_node_state, configuration.leases)

        configured_manifestations = this_node_config.manifestations

        configured_dataset_ids = set(
            manifestation.dataset.dataset_id
            for manifestation in configured_manifestations.values()
            # Don't create deleted datasets
            if not manifestation.dataset.deleted
        )

        local_dataset_ids = set(local_node_state.manifestations.keys())

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
            local_node_state.devices,
            configured_manifestations,
            cluster_state.nonmanifest_datasets,
            local_state.volumes
        ))
        mounts = list(self._calculate_mounts(
            local_node_state.devices, local_node_state.paths,
            configured_manifestations, local_state.volumes
        ))
        unmounts = list(self._calculate_unmounts(
            local_node_state.paths, configured_manifestations,
            local_state.volumes
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
            local_node_state.devices, local_node_state.paths,
            configured_manifestations, local_state.volumes
        ))
        deletes = self._calculate_deletes(
            local_node_state, configured_manifestations, local_state.volumes)

        # FLOC-1484 Support resize for block storage backends. See also
        # FLOC-1875.

        return in_parallel(changes=(
            not_in_use(unmounts) + detaches +
            attaches + mounts +
            creates + not_in_use(deletes)
        ))

    def _calculate_mounts(self, devices, paths, configured, volumes):
        """
        :param PMap devices: The datasets with volumes attached to this node
            and the device files at which they are available.  This is the same
            as ``NodeState.devices``.
        :param PMap paths: The paths at which datasets' filesystems are mounted
            on this node.  This is the same as ``NodeState.paths``.
        :param PMap configured: The manifestations which are configured on this
            node.  This is the same as ``NodeState.manifestations``.
        :param volumes: An iterable of ``BlockDeviceVolume`` instances that are
            known to exist in the cluster.

        :return: A generator of ``MountBlockDevice`` instances, one for each
            dataset which exists, is attached to this node, does not have its
            filesystem mounted, and is configured to have a manifestation on
            this node.
        """
        for configured_dataset_id in configured:
            if configured_dataset_id in paths:
                # It's mounted already.
                continue
            dataset_id = UUID(configured_dataset_id)
            if dataset_id in devices:
                # It's attached.
                path = self._mountpath_for_dataset_id(configured_dataset_id)
                volume = _blockdevice_volume_from_datasetid(volumes,
                                                            dataset_id)
                yield MountBlockDevice(
                    dataset_id=dataset_id,
                    blockdevice_id=volume.blockdevice_id,
                    mountpoint=path,
                )

    def _calculate_unmounts(self, paths, configured, volumes):
        """
        :param PMap paths: The paths at which datasets' filesystems are mounted
            on this node.  This is the same as ``NodeState.paths``.
        :param PMap configured: The manifestations which are configured on this
            node.  This is the same as ``NodeState.manifestations``.
        :param volumes: An iterable of ``BlockDeviceVolume`` instances that are
            known to exist in the cluster.

        :return: A generator of ``UnmountBlockDevice`` instances, one for each
            dataset which exists, is attached to this node, has its filesystem
            mount, and is configured to not have a manifestation on this node.
        """
        for mounted_dataset_id in paths:
            if mounted_dataset_id not in configured:
                dataset_id = UUID(mounted_dataset_id)
                volume = _blockdevice_volume_from_datasetid(volumes,
                                                            dataset_id)
                yield UnmountBlockDevice(dataset_id=dataset_id,
                                         blockdevice_id=volume.blockdevice_id)

    def _calculate_detaches(self, devices, paths, configured, volumes):
        """
        :param PMap devices: The datasets with volumes attached to this node
            and the device files at which they are available.  This is the same
            as ``NodeState.devices``.
        :param PMap paths: The paths at which datasets' filesystems are mounted
            on this node.  This is the same as ``NodeState.paths``.
        :param PMap configured: The manifestations which are configured on this
            node.  This is the same as ``NodeState.manifestations``.
        :param volumes: An iterable of ``BlockDeviceVolume`` instances that are
            known to exist in the cluster.

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
            volume = _blockdevice_volume_from_datasetid(volumes,
                                                        attached_dataset_id)
            yield DetachVolume(dataset_id=attached_dataset_id,
                               blockdevice_id=volume.blockdevice_id)

    def _calculate_attaches(self, devices, configured, nonmanifest, volumes):
        """
        :param PMap devices: The datasets with volumes attached to this node
            and the device files at which they are available.  This is the same
            as ``NodeState.devices``.
        :param PMap configured: The manifestations which are configured on this
            node.  This is the same as ``NodeState.manifestations``.
        :param PMap nonmanifest: The datasets which exist in the cluster but
            are not attached to any node.
        :param volumes: An iterable of ``BlockDeviceVolume`` instances that are
            known to exist in the cluster.

        :return: A generator of ``AttachVolume`` instances, one for each
                 dataset which exists, is unattached, and is configured to be
                 attached to this node.
        """
        for manifestation in configured.values():
            dataset_id = UUID(manifestation.dataset_id)
            if dataset_id in devices:
                # It's already attached here.
                continue
            if manifestation.dataset_id in nonmanifest:
                volume = _blockdevice_volume_from_datasetid(volumes,
                                                            dataset_id)
                # It exists and doesn't belong to anyone else.
                yield AttachVolume(
                    dataset_id=dataset_id,
                    blockdevice_id=volume.blockdevice_id,
                )

    def _calculate_deletes(self, local_node_state, configured_manifestations,
                           volumes):
        """
        :param NodeState: The local state discovered immediately prior to
            calculation.

        :param dict configured_manifestations: The manifestations configured
            for this node (like ``Node.manifestations``).

        :param volumes: An iterable of ``BlockDeviceVolume`` instances that are
            known to exist in the cluster.

        :return: A generator of ``DestroyBlockDeviceDataset`` instances for
            each volume that may need to be destroyed based on the given
            configuration.
        """
        delete_dataset_ids = set(
            manifestation.dataset.dataset_id
            for manifestation in configured_manifestations.values()
            if manifestation.dataset.deleted
        )
        for dataset_id_unicode in delete_dataset_ids:
            dataset_id = UUID(dataset_id_unicode)
            volume = _blockdevice_volume_from_datasetid(volumes, dataset_id)
            if (volume is not None and
                    dataset_id_unicode in local_node_state.manifestations):
                yield DestroyBlockDeviceDataset(
                    dataset_id=dataset_id,
                    blockdevice_id=volume.blockdevice_id)


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
