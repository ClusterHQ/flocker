# -*- test-case-name: flocker.node.agents.functional.test_ebs -*-
# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
An EBS implementation of the ``IBlockDeviceAPI``.
"""

from types import NoneType
from subprocess import check_output
import threading
import time
import logging
import itertools

# Don't use pyOpenSSL in urllib3 - it causes an ``OpenSSL.SSL.Error``
# exception when we try an API call on an idled persistent connection.
# See https://github.com/boto/boto3/issues/220
from botocore.vendored.requests.packages.urllib3.contrib.pyopenssl import (
    extract_from_urllib3,
)
extract_from_urllib3()

import boto3

from botocore.exceptions import ClientError, EndpointConnectionError

# There is no boto3 equivalent of this yet.
# See https://github.com/boto/boto3/issues/313
from boto.utils import get_instance_metadata

from uuid import UUID

from bitmath import Byte, GiB

from characteristic import with_cmp
from pyrsistent import PClass, field, pset, pmap, thaw
from zope.interface import implementer
from twisted.python.constants import (
    Names, NamedConstant, Values, ValueConstant
)
from twisted.python.filepath import FilePath

from eliot import Message, register_exception_extractor

from .blockdevice import (
    IBlockDeviceAPI, IProfiledBlockDeviceAPI, BlockDeviceVolume, UnknownVolume,
    AlreadyAttachedVolume, UnattachedVolume, UnknownInstanceID,
    MandatoryProfiles, ICloudAPI,
)

from ..script import StorageInitializationError

from ...control import pmap_field

from ._logging import (
    AWS_ACTION, NO_AVAILABLE_DEVICE,
    NO_NEW_DEVICE_IN_OS, WAITING_FOR_VOLUME_STATUS_CHANGE,
    BOTO_LOG_HEADER, IN_USE_DEVICES, CREATE_VOLUME_FAILURE,
    BOTO_LOG_RESULT
)

DATASET_ID_LABEL = u'flocker-dataset-id'
METADATA_VERSION_LABEL = u'flocker-metadata-version'
CLUSTER_ID_LABEL = u'flocker-cluster-id'
BOTO_NUM_RETRIES = 20
VOLUME_STATE_CHANGE_TIMEOUT = 300
MAX_ATTACH_RETRIES = 3

# Minimum IOPS per second for a provisioned IOPS volume.
IOPS_MIN_IOPS = 100
# Minimum size in GiB for a provisioned IPS volume.
IOPS_MIN_SIZE = 4

# http://docs.aws.amazon.com/AWSEC2/latest/APIReference/errors-overview.html
# for error details:
NOT_FOUND = u'InvalidVolume.NotFound'
INVALID_PARAMETER_VALUE = u'InvalidParameterValue'


# Register Eliot field extractor for ClientError responses.
register_exception_extractor(
    ClientError,
    lambda e: {
        "aws_code": e.response['Error']['Code'],
        "aws_message": unicode(e.response['Error']['Message']),
        "aws_request_id": e.response['ResponseMetadata']['RequestId'],
    }
)


class EBSVolumeTypes(Values):
    """
    Constants for the different types of volumes that can be created on EBS.
    These are taken from the documentation at:
    http://docs.aws.amazon.com/AWSEC2/latest/UserGuide/EBSVolumeTypes.html

    :ivar STANDARD: Magnetic

    :ivar IO1: Provisioned IOPS (SSD)

    :ivar GP2: General Purpose (SSD)
    """
    STANDARD = ValueConstant(u"standard")
    IO1 = ValueConstant(u"io1")
    GP2 = ValueConstant(u"gp2")


class EBSProfileAttributes(PClass):
    """
    Sets of profile attributes for the mandatory EBS volume profiles.

    :ivar volume_type: The volume_type for the boto create_volume call.
        Valid values are EBSVolumeTypes.

    :ivar iops_per_size_gib: The desired IOs per second per GiB of disk size.

    :ivar max_iops: The maximum number of IOs per second that EBS will accept
        for this type of volume.
    """
    volume_type = field(mandatory=False, type=ValueConstant,
                        initial=EBSVolumeTypes.STANDARD)
    iops_per_size_gib = field(mandatory=False,
                              type=(int, type(None)), initial=None)
    max_iops = field(mandatory=False, type=(int, type(None)), initial=None)

    def requested_iops(self, size_gib):
        """
        Returns the requested IOs per second for this profile or None if you
        cannot request a rate of IOs per second for this volume type. This will
        be iops_per_size_gib * size_gib unless this value exceeds max_iops.

        :param int size_gib: The size in GiB of the volume being created.

        :returns: The requested IOs per second for this profile for a disk of
            the given size.
        """
        if self.iops_per_size_gib is not None:
            if self.max_iops is not None:
                return min(size_gib * self.iops_per_size_gib,
                           self.max_iops)
            return size_gib * self.iops_per_size_gib
        return None


class EBSMandatoryProfileAttributes(Values):
    """
    These constants are the ``EBSProfileAttributes`` for the mandatory
    profiles. Many of the values for these were gotten from the documentation
    at:
    http://docs.aws.amazon.com/AWSEC2/latest/UserGuide/EBSVolumeTypes.html

    :ivar GOLD: The high performing Provisioned IOPS disks.
    :ivar SILVER: The medium performing SSD disks.
    :ivar BRONZE: The cheap magnetic disks.
    """
    GOLD = ValueConstant(EBSProfileAttributes(volume_type=EBSVolumeTypes.IO1,
                                              iops_per_size_gib=30,
                                              max_iops=20000))
    # ``gp2`` volume type cannot take IOPS request since it defaults to
    # baseline performance of 3 IOPS/GiB (up to 10,000 IOPS)
    SILVER = ValueConstant(EBSProfileAttributes(
        volume_type=EBSVolumeTypes.GP2))
    BRONZE = ValueConstant(EBSProfileAttributes(
        volume_type=EBSVolumeTypes.STANDARD))


def _volume_type_and_iops_for_profile_name(profile_name, size):
    """
    Determines and returns the volume_type and iops for a boto create_volume
    call for a given profile_name.

    :param profile_name: The name of the profile.

    :param size: The size of the volume to create in GiB.

    :returns: A tuple of (volume_type, iops) to be passed to a create_volume
        call.
    """
    volume_type = None
    iops = None
    try:
        A = EBSMandatoryProfileAttributes.lookupByName(
            MandatoryProfiles.lookupByValue(profile_name).name).value
    except ValueError:
        pass
    else:
        volume_type = A.volume_type.value
        iops = A.requested_iops(size)
    return volume_type, iops


class VolumeOperations(Names):
    """
    Supported EBS backend operations on a volume.
    """
    CREATE = NamedConstant()
    ATTACH = NamedConstant()
    DETACH = NamedConstant()
    DESTROY = NamedConstant()


class VolumeStates(Values):
    """
    Expected EBS volume states during ``VolumeOperations``.
    """
    EMPTY = ValueConstant('')
    CREATING = ValueConstant(u'creating')
    AVAILABLE = ValueConstant(u'available')
    ATTACHING = ValueConstant(u'attaching')
    IN_USE = ValueConstant(u'in-use')
    DETACHING = ValueConstant(u'detaching')
    DELETING = ValueConstant(u'deleting')


class VolumeStateFlow(PClass):
    """
    Expected EBS volume state flow during ``VolumeOperations``.
    """
    start_state = field(mandatory=True, type=ValueConstant)
    transient_state = field(mandatory=True, type=ValueConstant)
    end_state = field(mandatory=True, type=ValueConstant)

    # Boolean flag to indicate if a volume state transition
    # results in non-empty ``attach_data.device`` and
    # ``attach_data.instance_id`` for the EBS volume.
    sets_attach = field(mandatory=True, type=bool)
    unsets_attach = field(mandatory=True, type=bool)


class VolumeStateTable(PClass):
    """
    Map of volume operation to expected volume state transitions
    and expected update to volume's ``attach_data``.
    """

    def _populate_volume_state_table():
        """
        Initialize volume state table  with transitions for ``create_volume``,
        ``attach_volume``, ``detach_volume``, ``delete_volume`` operations.
        """
        O = VolumeOperations
        S = VolumeStates
        table = pmap()

        def add_flow(operation, start, transient, end, sets_attach,
                     unsets_attach):
            """
            Helper to add expected volume states for given operation.
            """
            return table.set(operation,
                             VolumeStateFlow(start_state=start,
                                             transient_state=transient,
                                             end_state=end,
                                             sets_attach=sets_attach,
                                             unsets_attach=unsets_attach))

        table = add_flow(O.CREATE, S.EMPTY, S.CREATING, S.AVAILABLE,
                         False, False)
        table = add_flow(O.ATTACH, S.AVAILABLE, S.ATTACHING, S.IN_USE,
                         True, False)
        table = add_flow(O.DETACH, S.IN_USE, S.DETACHING, S.AVAILABLE,
                         False, True)
        table = add_flow(O.DESTROY, S.AVAILABLE, S.DELETING, S.EMPTY,
                         False, False)
        return table

    table = pmap_field(NamedConstant, VolumeStateFlow,
                       initial=_populate_volume_state_table())

VOLUME_STATE_TABLE = VolumeStateTable()


class AttachFailed(Exception):
    """
    AWS EBS refused to allow a volume to be attached to an instance.
    """


class InvalidRegionError(Exception):
    """
    The supplied region is not a valid AWS endpoint.
    """
    def __init__(self, region):
        message = u"The specified AWS region is not valid."
        Exception.__init__(self, message, region)
        self.region = region


class InvalidZoneError(Exception):
    """
    The supplied zone is not valid for the given AWS region.
    """
    def __init__(self, zone, available_zones):
        message = u"The specified AWS zone is not valid."
        Exception.__init__(
            self, message, zone, u"Available zones:", available_zones)
        self.zone = zone
        self.available_zones = available_zones


class InvalidStateException(Exception):
    """
    A volume is not in an appropriate state to perform an operation.

    :param boto3.resources.factory.ec2.Volume volume: The volume.
    :param str state: The known volume state at the time of the exception.
    :param list valid_states: A ``list`` of ``str`` representing states
        that would have been valid for this operation.
    """
    def __init__(self, volume, state, valid_states):
        Exception.__init__(self, volume, state, valid_states)
        self.volume = volume
        self.state = state
        self.valid_states = valid_states


class TagNotFound(Exception):
    """
    A named tag could not be found an a volume.

    :param str volume_id: The ID of the volume.
    :param str tag: The name of the tag that could not be found.
    :param list existing_tags: The tags that do exist on the volume.
    """
    def __init__(self, volume_id, tag, existing_tags):
        Exception.__init__(self, volume_id, tag, existing_tags)
        self.volume_id = volume_id
        self.tag = tag
        self.existing_tags = existing_tags


class TimeoutException(Exception):
    """
    A timeout on waiting for volume to reach destination end state.

    :param unicode blockdevice_id: Unique identifier for a volume.
    :param NamedConstant operation: Operation performed on volume.
    :param unicode start_state: Volume's start state before operation.
    :param unicode transient_state: Expected transient state during operation.
    :param unicode end_state: Expected end state on operation completion.
    :param unicode current_state: Volume's state at timeout.
    """
    def __init__(self, blockdevice_id, operation,
                 start_state, transient_state, end_state, current_state):
        Exception.__init__(self, blockdevice_id, operation, current_state)
        self.blockdevice_id = blockdevice_id
        self.operation = operation
        self.start_state = start_state
        self.transient_state = transient_state
        self.end_state = end_state
        self.current_state = current_state


class UnexpectedStateException(Exception):
    """
    An unexpected state was encountered by a volume as a result of operation.

    :param unicode blockdevice_id: Unique identifier for a volume.
    :param NamedConstant operation: Operation performed on volume.
    :param unicode start_state: Volume's start state before operation.
    :param unicode transient_state: Expected transient state during operation.
    :param unicode end_state: Expected end state on operation completion.
    :param unicode current_state: Volume's state at timeout.
    """
    def __init__(self, blockdevice_id, operation,
                 start_state, transient_state, end_state, current_state):
        Exception.__init__(self, blockdevice_id, operation, current_state)
        self.blockdevice_id = blockdevice_id
        self.operation = operation
        self.start_state = start_state
        self.transient_state = transient_state
        self.end_state = end_state
        self.current_state = current_state


class EliotLogHandler(logging.Handler):
    def emit(self, record):
        Message.new(
            message_type=BOTO_LOG_HEADER, message=record.getMessage()
        ).write()


def _enable_boto_logging():
    """
    Make boto log activity using Eliot.
    """
    logger = logging.getLogger("boto3")
    logger.setLevel(logging.INFO)
    logger.addHandler(EliotLogHandler())

_enable_boto_logging()


@with_cmp(["requested", "discovered"])
class AttachedUnexpectedDevice(Exception):
    """
    A volume was attached to a device other than the one we expected.

    :ivar str _template: A native string giving the template into which to
        format attributes for the string representation.
    """
    _template = "AttachedUnexpectedDevice(requested={!r}, discovered={!r})"

    def __init__(self, requested, discovered):
        """
        :param FilePath requested: The requested device name.
        :param discovered: A ``FilePath`` giving the path of the device which
            was discovered on the system or ``None`` if no new device was
            discovered at all.
        """
        # It would be cool to replace this logic with pyrsistent typed fields
        # but Exception and PClass have incompatible layouts (you can't have an
        # exception that's a PClass).
        if not isinstance(requested, FilePath):
            raise TypeError(
                "requested must be FilePath, not {}".format(type(requested))
            )
        if not isinstance(discovered, (FilePath, NoneType)):
            raise TypeError(
                "discovered must be None or FilePath, not {}".format(
                    type(discovered)
                )
            )

        self.requested = requested
        self.discovered = discovered

    def __str__(self):
        discovered = self.discovered
        if discovered is not None:
            discovered = discovered.path
        return self._template.format(
            self.requested.path, discovered,
        )

    __repr__ = __str__


def _expected_device(requested_device):
    """
    Given a device we requested from AWS EBS, determine the OS device path that
    will actually be created.

    This maps EBS required ``/dev/sdX`` names to ``/dev/vbdX`` names that are
    used by currently supported platforms (Ubuntu 14.04 and CentOS 7).
    """
    prefix = b"/dev/sd"
    if requested_device.startswith(prefix):
        return FilePath(b"/dev").child(b"xvd" + requested_device[len(prefix):])
    raise ValueError(
        "Unsupported requested device {!r}".format(requested_device)
    )


def ec2_client(region, zone, access_key_id,
               secret_access_key, validate_region=True):
    """
    Establish connection to EC2 client.

    :param str region: The name of the EC2 region to connect to.
    :param str zone: The zone for the EC2 region to connect to.
    :param str access_key_id: "aws_access_key_id" credential for EC2.
    :param str secret_access_key: "aws_secret_access_key" EC2 credential.
    :param bool validate_region: Flag indicating whether to validate the
        region and zone by calling out to AWS.

    :return: An ``_EC2`` giving information about EC2 client connection
        and EC2 instance zone.
    """
    # Set a retry option in Botocore to BOTO_NUM_RETRIES:
    # ``metadata_service_num_attempts``:
    # Request for retry attempts by Boto to
    # retrieve data from Metadata Service used to retrieve
    # credentials for IAM roles on EC2 instances.
    # Exponential backoff and retry for ``RequestLimitExceeded``
    # errors is already set in botocore.
    connection = boto3.session.Session(
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key
    )
    connection._session.set_config_variable(
        'metadata_service_num_attempts', BOTO_NUM_RETRIES)
    ec2_resource = connection.resource("ec2", region_name=region)
    if validate_region:
        try:
            zones = ec2_resource.meta.client.describe_availability_zones()
        except EndpointConnectionError:
            raise InvalidRegionError(region)
        available_zones = [
            available_zone['ZoneName']
            for available_zone in zones['AvailabilityZones']
        ]
        if zone not in available_zones:
            raise InvalidZoneError(zone, available_zones)
    return _EC2(zone=zone, connection=ec2_resource)


def boto3_log(method):
    """
    Decorator to run a boto3.ec2.ServiceResource method and
    log additional information about any exceptions that are raised.

    :param func method_name: The method to call.

    :return: A function which will call the method and do
        the extra exception logging.
    """
    def _run_with_logging(*args, **kwargs):
        """
        Run given boto3.ec2.ServiceResource method with exception
        logging for ``ClientError``.
        """
        with AWS_ACTION(operation=[method.__name__, args[1:], kwargs]):
            return method(*args, **kwargs)
    return _run_with_logging


def _get_volume_tag(volume, name):
    """
    Retrieve the tag from the specified volume with the specified name.

    :param Volume volume: The volume.
    :param unicode name: The tag name.

    :return: A ``str`` representing the value of the tag.
    """
    for tag in volume.tags:
        if tag['Key'] == name:
            return tag['Value']
    raise TagNotFound(volume.id, name, volume.tags)


class _EC2(PClass):
    """
    :ivar str zone: The name of the zone for the connection.
    :ivar boto3.resources.factory.ec2.ServiceResource: Object
        representing an EC2 resource.
    """
    zone = field(mandatory=True)
    connection = field(mandatory=True)


def _blockdevicevolume_from_ebs_volume(ebs_volume):
    """
    Helper function to convert Volume information from
    EBS format to Flocker block device format.

    :param boto3.resources.factory.ec2.Volume ebs_volume:
        Volume in EC2 format.

    :return: Input volume in BlockDeviceVolume format.
    """
    if ebs_volume.attachments:
        attached_to = unicode(ebs_volume.attachments[0]['InstanceId'])
    else:
        attached_to = None

    volume_dataset_id = _get_volume_tag(ebs_volume, DATASET_ID_LABEL)

    return BlockDeviceVolume(
        blockdevice_id=unicode(ebs_volume.id),
        size=int(GiB(ebs_volume.size).to_Byte().value),
        attached_to=attached_to,
        dataset_id=UUID(volume_dataset_id)
    )


def _get_ebs_volume_state(volume):
    """
    Fetch input EBS volume's latest state from backend.

    :param boto3.resources.factory.ec2.Volume: Volume that needs state update.

    :returns: EBS volume with latest state known to backend.
    :rtype: boto3.resources.factory.ec2.Volume

    """
    volume.reload()
    return volume


def _should_finish(operation, volume, update, start_time,
                   timeout=VOLUME_STATE_CHANGE_TIMEOUT):
    """
    Helper function to determine if wait for volume's state transition
    resulting from given operation is over.
    The method completes if volume reached expected end state, or, failed
    to reach expected end state, or we timed out waiting for the volume to
    reach expected end state.

    :param NamedConstant operation: Operation performed on given volume.
    :param boto3.resources.factory.ec2.Volume: Target volume of given
        operation.
    :param method update: Method to use to check volume state.
    :param float start_time: Time when operation was executed on volume.
    :param int timeout: Time, in seconds, to wait for volume to reach expected
        destination state.

    :returns: True or False indicating end of wait for volume state transition.
    :rtype: bool
    """
    state_flow = VOLUME_STATE_TABLE.table[operation]
    start_state = state_flow.start_state.value
    transient_state = state_flow.transient_state.value
    end_state = state_flow.end_state.value
    sets_attach = state_flow.sets_attach
    unsets_attach = state_flow.unsets_attach

    if time.time() - start_time > timeout:
        # We either:
        # 1) Timed out waiting to reach ``end_status``, or,
        # 2) Reached an unexpected status (state change resulted in error), or,
        # 3) Reached ``end_status``, but ``end_status`` comes with
        #    attach data, and we timed out waiting for attach data.
        # Raise a ``TimeoutException`` in all cases.
        raise TimeoutException(unicode(volume.id), operation, start_state,
                               transient_state, end_state, volume.state)

    try:
        update(volume)
    except ClientError as e:
        # If AWS cannot find the volume, raise ``UnknownVolume``.
        if e.response['Error']['Code'] == NOT_FOUND:
            raise UnknownVolume(volume.id)

    if volume.state not in [start_state, transient_state, end_state]:
        raise UnexpectedStateException(unicode(volume.id), operation,
                                       start_state, transient_state, end_state,
                                       volume.state)
    if volume.state != end_state:
        return False

    # If end state for the volume comes with attach data,
    # declare success only upon discovering attach data.
    if volume.attachments:
        volume_attach_data = volume.attachments[0]
    else:
        volume_attach_data = None
    if sets_attach:
        return (volume_attach_data is not None and
                (volume_attach_data['Device'] != '' and
                 volume_attach_data['InstanceId'] != ''))
    elif unsets_attach:
        return (volume_attach_data is None or
                (volume_attach_data['Device'] == '' and
                 volume_attach_data['InstanceId'] == ''))
    else:
        return True


def _wait_for_volume_state_change(operation,
                                  volume,
                                  update=_get_ebs_volume_state,
                                  timeout=VOLUME_STATE_CHANGE_TIMEOUT):
    """
    Helper function to wait for a given volume to change state
    from ``start_status`` via ``transient_status`` to ``end_status``.

    :param NamedConstant operation: Operation triggering volume state change.
        A value from ``VolumeOperations``.
    :param boto3.resources.factory.ec2.Volume: Volume to check status for.
    :param update: Method to use to fetch EBS volume's latest state.
    :param int timeout: Seconds to wait for volume operation to succeed.

    :raises Exception: When input volume fails to reach expected backend
        state for given operation within timeout seconds.
    """
    # It typically takes a few seconds for anything to happen, so start
    # out sleeping a little before doing initial check to reduce
    # unnecessary polling of the API:
    time.sleep(5.0)

    # Wait ``timeout`` seconds for
    # volume status to transition from
    # start_status -> transient_status -> end_status.
    start_time = time.time()
    while not _should_finish(operation, volume, update, start_time, timeout):
        time.sleep(1.0)
        WAITING_FOR_VOLUME_STATUS_CHANGE(volume_id=volume.id,
                                         status=volume.state,
                                         wait_time=(time.time() - start_time))


def _get_device_size(device):
    """
    Helper function to fetch the size of given block device.

    :param unicode device: Name of the block device to fetch size for.

    :returns: Size, in SI metric bytes, of device we are interested in.
    :rtype: int
    """
    device_name = b"/dev/" + device.encode("ascii")

    # Retrieve size of device as OS sees it using `lsblk`.
    # Requires util-linux-ng package on CentOS, and
    # util-linux on Ubuntu.
    # Required package is installed by default
    # on Ubuntu 14.04 and CentOS 7.
    command = [b"/bin/lsblk", b"--noheadings", b"--bytes",
               b"--output", b"SIZE", device_name]

    # Get the base device size, which is the first line in
    # `lsblk` output. Ignore partition sizes.
    # XXX: Handle error cases during `check_output()` run
    # (https://clusterhq.atlassian.net/browse/FLOC-1886).
    command_output = check_output(command).split(b'\n')[0]
    device_size = int(command_output.strip().decode("ascii"))

    return device_size


def _wait_for_new_device(base, size, time_limit=60):
    """
    Helper function to wait for up to 60s for new
    EBS block device (`/dev/sd*` or `/dev/xvd*`) to
    manifest in the OS.

    :param list base: List of baseline block devices
        that existed before execution of operation that expects
        to create a new block device.
    :param int size: Size of the block device we are expected
        to manifest in the OS.
    :param int time_limit: Time, in seconds, to wait for
        new device to manifest. Defaults to 60s.

    :returns: The path of the new block device file.
    :rtype: ``FilePath``
    """
    start_time = time.time()
    elapsed_time = time.time() - start_time
    while elapsed_time < time_limit:
        for device in list(set(FilePath(b"/sys/block").children()) -
                           set(base)):
            device_name = FilePath.basename(device)
            if (device_name.startswith((b"sd", b"xvd")) and
                    _get_device_size(device_name) == size):
                return FilePath(b"/dev").child(device_name)
        time.sleep(0.1)
        elapsed_time = time.time() - start_time

    # If we failed to find a new device of expected size,
    # log sizes of all new devices on this compute instance,
    # for debuggability.
    new_devices = list(set(FilePath(b"/sys/block").children()) - set(base))
    new_devices_size = [_get_device_size(device) for device in new_devices]
    NO_NEW_DEVICE_IN_OS(new_devices=new_devices,
                        new_devices_size=new_devices_size,
                        expected_size=size,
                        time_limit=time_limit).write()
    return None


def _is_cluster_volume(cluster_id, ebs_volume):
    """
    Helper function to check if given volume belongs to
    given cluster.

    :param UUID cluster_id: UUID of Flocker cluster to check for
        membership.
    :param boto3.resources.factory.ec2.Volume ebs_volume: EBS volume to check
        for input cluster membership.

    :return bool: True if input volume belongs to input
        Flocker cluster. False otherwise.
    """
    if ebs_volume.tags is not None:
        actual_cluster_id = [
            tag['Value'] for tag in ebs_volume.tags
            if tag['Key'] == CLUSTER_ID_LABEL
        ]
        if actual_cluster_id:
            actual_cluster_id = UUID(actual_cluster_id.pop())
            if actual_cluster_id == cluster_id:
                return True
    return False


def _attach_volume_and_wait_for_device(
    volume, attach_to, attach_volume,
    detach_volume, device, blockdevices,
):
    """
    Attempt to attach an EBS volume to an EC2 instance and wait for the
    corresponding OS device to become available.

    :param BlockDeviceVolume volume: The Flocker representation of the volume
        to attach.
    :param unicode attach_to: The EC2 instance id to which to attach it.
    :param attach_volume: A function like ``EC2Connection.attach_volume``.
    :param detach_volume: A function like ``EC2Connection.detach_volume``.
    :param unicode device: The OS device path to which to attach the device.
    :param list blockdevices: The OS device paths (as ``FilePath``) which are
        already present on the system before this operation is attempted
        (primarily useful to make testing easier).

    :raise: Anything ``attach_volume`` can raise.  Or
        ``AttachedUnexpectedDevice`` if the volume appears to become attached
        to the wrong OS device file.

    :return: ``True`` if the volume is attached and accessible via the expected
        OS device file.  ``False`` if the attempt times out without succeeding.
    """
    try:
        attach_volume(volume.blockdevice_id, attach_to, device)
    except ClientError as e:
        # If attach failed that is often because of eventual
        # consistency in AWS, so let's ignore this one if it
        # fails:
        if e.response['Error']['Code'] == u'InvalidParameterValue':
            return False
        raise
    else:
        # Wait for new device to manifest in the OS. Since there
        # is currently no standardized protocol across Linux guests
        # in EC2 for mapping `device` to the name device driver
        # picked (http://docs.aws.amazon.com/AWSEC2/latest/
        # UserGuide/device_naming.html), wait for new block device
        # to be available to the OS, and interpret it as ours.
        # Wait under lock scope to reduce false positives.
        device_path = _wait_for_new_device(
            blockdevices, volume.size
        )
        # We do, however, expect the attached device name to follow
        # a certain simple pattern.  Verify that now and signal an
        # error immediately if the assumption is violated.  If we
        # let it go by, a later call to ``get_device_path`` will
        # quietly produce the wrong results.
        #
        # To make this explicit, we *expect* that the device will
        # *always* be what we *expect* the device to be (sorry).
        # This check is only here in case we're wrong to make the
        # system fail in a less damaging way.
        if _expected_device(device) != device_path:
            # We also don't want anything to re-discover the volume
            # in an attached state since that might also result in
            # use of ``get_device_path`` (producing an incorrect
            # result).  This is a best-effort.  It's possible the
            # agent will crash after attaching the volume and
            # before detaching it here, leaving the system in a bad
            # state.  This is one reason we need a better solution
            # in the long term.
            detach_volume(volume.blockdevice_id)
            raise AttachedUnexpectedDevice(FilePath(device), device_path)
        return True


def _get_blockdevices():
    return FilePath(b"/sys/block").children()


@implementer(IBlockDeviceAPI)
@implementer(IProfiledBlockDeviceAPI)
@implementer(ICloudAPI)
class EBSBlockDeviceAPI(object):
    """
    An EBS implementation of ``IBlockDeviceAPI`` which creates
    block devices in an EC2 cluster using Boto APIs.
    """
    def __init__(self, ec2_client, cluster_id):
        """
        Initialize EBS block device API instance.

        :param _EC2 ec2_client: A record of EC2 connection and zone.
        :param UUID cluster_id: UUID of cluster for this
            API instance.
        """
        self.connection = ec2_client.connection
        self.zone = ec2_client.zone
        self.cluster_id = cluster_id
        self.lock = threading.Lock()

    def allocation_unit(self):
        """
        Return a fixed allocation_unit for now; one which we observe
        to work on AWS.
        """
        return int(GiB(1).to_Byte().value)

    @boto3_log
    def compute_instance_id(self):
        """
        Look up the EC2 instance ID for this node.
        """
        instance_id = get_instance_metadata().get('instance-id', None)
        if instance_id is None:
            raise UnknownInstanceID(self)
        return instance_id.decode("ascii")

    @boto3_log
    def _create_ebs_volume(
        self, size=1, volume_type=EBSVolumeTypes.STANDARD.value,
        zone=None, iops=None
    ):
        """
        Create a new EC2 volume with the specified parameters.

        :param int size: Volume size in GiB. For provisioned IOPS volumes,
            this is a minimum of 4.
        :param str volume_type: The type of volume to create.
            This can be 'gp2' for General Purpose (SSD) volumes,
            'io1' for Provisioned IOPS (SSD) volumes, or 'standard'
            for Magnetic volumes.
        :param str zone: The availability zone where this volume will be
            created. If not specified, the default zone of this client.
        :param int iops: If creating a provisioned IOPS volume, the
            The number of I/O operations per second to provision,
            with a maximum ratio of 30 IOPS/GiB.

        :return: The ``Volume`` representation of the created volume.
        """
        if zone is None:
            zone = self.zone
        client = self.connection.meta.client
        if volume_type == EBSVolumeTypes.IO1.value:
            if iops is None:
                iops = IOPS_MIN_IOPS
            if size < IOPS_MIN_SIZE:
                size = IOPS_MIN_SIZE
            volume_data = client.create_volume(
                Size=size,
                AvailabilityZone=zone,
                VolumeType=volume_type,
                Iops=iops
            )
        else:
            volume_data = client.create_volume(
                Size=size,
                AvailabilityZone=zone,
                VolumeType=volume_type
            )
        volume = self.connection.Volume(volume_data['VolumeId'])
        volume.load()
        return volume

    @boto3_log
    def _list_ebs_volumes(self, page_size=100):
        """
        List all the volumes associated with this client's region.
        Volumes are retrieved in lists limited to the specified page size,
        then amalgamated to return a single list of all volumes.

        :param int page_size: Maximum page size of each list of volumes.

        :return: A ``list`` of ``Volume`` objects.
        """
        return list(itertools.chain.from_iterable(list(
            volumes for volumes in
            self.connection.volumes.page_size(page_size).pages()
        )))

    @boto3_log
    def _get_ebs_volume(self, blockdevice_id):
        """
        Lookup EBS Volume information for a given blockdevice_id.

        :param unicode blockdevice_id: ID of a blockdevice that needs lookup.

        :returns: boto.ec2.volume.Volume for the input id.

        :raise UnknownVolume: If no volume with a matching identifier can be
             found.
        """
        try:
            volume = self.connection.Volume(blockdevice_id)
            volume.load()
            return volume
        except ClientError as e:
            if e.response['Error']['Code'] == NOT_FOUND:
                raise UnknownVolume(blockdevice_id)
            else:
                raise

    @boto3_log
    def _detach_ebs_volume(self, volume_id):
        """
        Detach the specified volume ID from an instance.

        :param str volume_id: The volume ID.
        :return: A ``dict`` containing the EC2 response data.
        """
        volume = self.connection.Volume(volume_id)
        return volume.detach_from_instance()

    @boto3_log
    def _attach_ebs_volume(self, volume_id, instance_id, device):
        """
        Attach a volume to an instance.

        :param str volume_id: The volume ID.
        :param str instance_id: The instance ID.
        :param unicode device: The OS device path to which to attach
            the device.

        :return: A ``dict`` containing the EC2 response data.
        """
        volume = self.connection.Volume(volume_id)
        return volume.attach_to_instance(
            InstanceId=instance_id, Device=device)

    def _next_device(self, instance_id, volumes, devices_in_use):
        """
        Get the next available EBS device name for a given EC2 instance.

        Algorithm:
        1. Get all ``Block devices`` currently in use by given instance:
            a) List all volumes visible to this instance.
            b) Gather device IDs of all devices attached to (a).
        2. Devices available for EBS volume usage are ``/dev/sd[f-p]``.
           Find the first device from this set that is currently not
           in use.
        XXX: Handle lack of free devices in ``/dev/sd[f-p]`` range
        (see https://clusterhq.atlassian.net/browse/FLOC-1887).

        :param unicode instance_id: EC2 instance ID.
        :param volumes: Collection of currently known
            ``BlockDeviceVolume`` instances.
        :param set devices_in_use: Unicode names of devices that are
            probably in use based on observed behavior.

        :returns unicode file_name: available device name for attaching
            EBS volume.
        :returns ``None`` if suitable EBS device names on this EC2
            instance are currently occupied.
        """
        volume_devices = []
        for v in volumes:
            volume_attachments = v.attachments
            for attachment in volume_attachments:
                if attachment['InstanceId'] == instance_id:
                    volume_devices.append(attachment['Device'])
        devices = pset(volume_devices)
        devices = devices | devices_in_use
        sorted_devices = sorted(list(thaw(devices)))
        IN_USE_DEVICES(devices=sorted_devices).write()

        for suffix in b"fghijklmonp":
            file_name = u'/dev/sd' + suffix
            if file_name not in devices:
                return file_name

        # Could not find any suitable device that is available
        # for attachment. Log to Eliot before giving up.
        NO_AVAILABLE_DEVICE(devices=sorted_devices).write()
        return None

    def create_volume(self, dataset_id, size):
        """
        Create a volume on EBS backend.
        """
        return self.create_volume_with_profile(
            dataset_id, size, MandatoryProfiles.DEFAULT.value)

    def create_volume_with_profile(self, dataset_id, size, profile_name):
        """
        Create a volume on EBS. Store Flocker-specific
        {metadata version, cluster id, dataset id} for the volume
        as volume tag data.
        Open issues: https://clusterhq.atlassian.net/browse/FLOC-1792
        """
        requested_size = int(Byte(size).to_GiB().value)
        try:
            volume_type, iops = _volume_type_and_iops_for_profile_name(
                profile_name, requested_size)
            requested_volume = self._create_ebs_volume(
                size=requested_size,
                zone=self.zone,
                volume_type=volume_type,
                iops=iops)
        except ClientError as e:
            # If we failed to create a volume with attributes complying
            # with requested profile, make a second attempt at volume
            # creation with default profile.
            # Compliance violation of the volume's requested profile
            # will be detected and remediated in a future release (FLOC-3275).
            if e.response['Error']['Code'] != INVALID_PARAMETER_VALUE:
                raise e
            CREATE_VOLUME_FAILURE(
                dataset_id=unicode(dataset_id),
                aws_code=e.response['Error']['Code'],
                aws_message=unicode(e.response['Error']['Message'])
            ).write()
            volume_type, iops = _volume_type_and_iops_for_profile_name(
                MandatoryProfiles.DEFAULT.value, requested_size)
            requested_volume = self._create_ebs_volume(
                size=requested_size,
                zone=self.zone,
                volume_type=volume_type,
                iops=iops)

        message_type = BOTO_LOG_RESULT + u':created_volume'
        Message.new(
            message_type=message_type, volume_id=unicode(requested_volume.id),
            dataset_id=unicode(dataset_id), size=unicode(size)
        ).write()

        # Stamp created volume with Flocker-specific tags.
        metadata = {
            METADATA_VERSION_LABEL: '1',
            CLUSTER_ID_LABEL: unicode(self.cluster_id),
            DATASET_ID_LABEL: unicode(dataset_id),
            # EC2 convention for naming objects, e.g. as used in EC2 web
            # console (http://stackoverflow.com/a/12798180).
            "Name": u"flocker-{}".format(dataset_id),
        }
        tags_list = []
        for key, value in metadata.items():
            tags_list.append(dict(Key=key, Value=value))
        requested_volume.create_tags(Tags=tags_list)

        message_type = BOTO_LOG_RESULT + u':created_tags'
        Message.new(
            message_type=message_type,
            requested_volume=requested_volume.id,
            tags=metadata
        ).write()

        # Wait for created volume to reach 'available' state.
        _wait_for_volume_state_change(VolumeOperations.CREATE,
                                      requested_volume)

        # Return created volume in BlockDeviceVolume format.
        return _blockdevicevolume_from_ebs_volume(requested_volume)

    def list_volumes(self):
        """
        Return all volumes that belong to this Flocker cluster.
        """
        try:
            ebs_volumes = self._list_ebs_volumes()
            message_type = BOTO_LOG_RESULT + u':listed_volumes'
            Message.new(
                message_type=message_type,
                volume_ids=list(volume.id for volume in ebs_volumes),
            ).write()
        except ClientError as e:
            # Work around some internal race-condition in EBS by retrying,
            # since this error makes no sense:
            if e.response['Error']['Code'] == NOT_FOUND:
                return self.list_volumes()
            else:
                raise

        volumes = []
        for ebs_volume in ebs_volumes:
            if _is_cluster_volume(self.cluster_id, ebs_volume):
                volumes.append(
                    _blockdevicevolume_from_ebs_volume(ebs_volume)
                )
        message_type = BOTO_LOG_RESULT + u':listed_cluster_volumes'
        Message.new(
            message_type=message_type,
            volume_ids=list(volume.blockdevice_id for volume in volumes),
        ).write()
        return volumes

    def attach_volume(self, blockdevice_id, attach_to):
        """
        Attach an EBS volume to given compute instance.

        :param unicode blockdevice_id: EBS UUID for volume to be attached.
        :param unicode attach_to: Instance id of AWS Compute instance to
            attached the blockdevice to.

        :raises UnknownVolume: If there does not exist a BlockDeviceVolume
            corresponding to the input blockdevice_id.
        :raises AlreadyAttachedVolume: If the input volume is already attached
            to a device.
        :raises AttachFailed: If the volume could not be attached.
        :raises AttachedUnexpectedDevice: If the attach operation fails to
            associate the volume with the expected OS device file.  This
            indicates use on an unsupported OS, a misunderstanding of the EBS
            device assignment rules, or some other bug in this implementation.
        """
        ebs_volume = self._get_ebs_volume(blockdevice_id)
        volume = _blockdevicevolume_from_ebs_volume(ebs_volume)
        if (volume.attached_to is not None or
                ebs_volume.state != VolumeStates.AVAILABLE.value):
            raise AlreadyAttachedVolume(blockdevice_id)

        attached = False
        ignore_devices = pset([])
        for attach_attempt in range(3):
            with self.lock:
                volumes = self._list_ebs_volumes()
                device = self._next_device(attach_to, volumes, ignore_devices)
                if device is None:
                    # XXX: Handle lack of free devices in ``/dev/sd[f-p]``.
                    # (https://clusterhq.atlassian.net/browse/FLOC-1887).
                    # No point in attempting an ``attach_volume``, return.
                    return
                blockdevices = _get_blockdevices()
                attached = _attach_volume_and_wait_for_device(
                    volume, attach_to,
                    self._attach_ebs_volume,
                    self._detach_ebs_volume,
                    device, blockdevices,
                )
                if attached:
                    _wait_for_volume_state_change(
                        VolumeOperations.ATTACH, ebs_volume,
                    )
                    attached_volume = volume.set('attached_to', attach_to)
                    return attached_volume
                else:
                    ignore_devices = ignore_devices.add(device)

        raise AttachFailed(volume.blockdevice_id, attach_to, device)

    def detach_volume(self, blockdevice_id):
        """
        Detach EBS volume identified by blockdevice_id.

        :param unicode blockdevice_id: EBS UUID for volume to be detached.

        :raises UnknownVolume: If there does not exist a BlockDeviceVolume
            corresponding to the input blockdevice_id.
        :raises UnattachedVolume: If the BlockDeviceVolume for the
            blockdevice_id is not currently 'in-use'.
        """
        ebs_volume = self._get_ebs_volume(blockdevice_id)
        if ebs_volume.state != VolumeStates.IN_USE.value:
            raise UnattachedVolume(blockdevice_id)

        self._detach_ebs_volume(blockdevice_id)

        _wait_for_volume_state_change(VolumeOperations.DETACH, ebs_volume)

    @boto3_log
    def destroy_volume(self, blockdevice_id):
        """
        Destroy EBS volume identified by blockdevice_id.

        :param String blockdevice_id: EBS UUID for volume to be destroyed.

        :raises UnknownVolume: If there does not exist a Flocker cluster
            volume identified by input blockdevice_id.
        :raises Exception: If we failed to destroy Flocker cluster volume
            corresponding to input blockdevice_id.
        """
        destroy_result = None
        ebs_volume = self._get_ebs_volume(blockdevice_id)
        ebs_volume.load()
        if ebs_volume.state == 'available':
            destroy_result = ebs_volume.delete()
        else:
            raise InvalidStateException(
                ebs_volume, ebs_volume.state, ['available'])
        if destroy_result:
            try:
                _wait_for_volume_state_change(VolumeOperations.DESTROY,
                                              ebs_volume)
            except UnknownVolume:
                return
        else:
            raise Exception(
                'Failed to delete volume: {!r}'.format(blockdevice_id)
            )

    def get_device_path(self, blockdevice_id):
        """
        Get device path for the EBS volume corresponding to the given
        block device.

        :param unicode blockdevice_id: EBS UUID for the volume to look up.

        :returns: A ``FilePath`` for the device.
        :raises UnknownVolume: If the supplied ``blockdevice_id`` does not
            exist.
        :raises UnattachedVolume: If the supplied ``blockdevice_id`` is
            not attached to a host.
        """
        ebs_volume = self._get_ebs_volume(blockdevice_id)
        volume = _blockdevicevolume_from_ebs_volume(ebs_volume)
        if not volume.attached_to:
            raise UnattachedVolume(blockdevice_id)

        compute_instance_id = self.compute_instance_id()
        if volume.attached_to != compute_instance_id:
            # This is untested.  See FLOC-2453.
            raise Exception(
                "Volume is attached to {}, not to {}".format(
                    volume.attached_to, compute_instance_id
                )
            )

        return _expected_device(ebs_volume.attachments[0]['Device'])

    # ICloudAPI:
    @boto3_log
    def list_live_nodes(self):
        instances = self.connection.instances.filter(
            Filters=[{'Name': 'instance-state-name', 'Values': ['running']}])
        return list(instance.id for instance in instances)


def aws_from_configuration(region, zone, access_key_id, secret_access_key,
                           cluster_id, validate_region=True):
    """
    Build an ``EBSBlockDeviceAPI`` instance using configuration and
    credentials.

    :param str region: The EC2 region slug.  Volumes will be manipulated in
        this region.
    :param str zone: The EC2 availability zone.  Volumes will be manipulated in
        this zone.
    :param str access_key_id: The EC2 API key identifier to use to make AWS API
        calls.
    :param str secret_access_key: The EC2 API key to use to make AWS API calls.
    :param UUID cluster_id: The unique identifier of the cluster with which to
        associate the resulting object.  It will only manipulate volumes
        belonging to this cluster.
    :param bool validate_region: If False, do not attempt to validate the
        region and zone by calling out to AWS. Useful for testing.

    :return: A ``EBSBlockDeviceAPI`` instance using the given parameters.
    """
    try:
        return EBSBlockDeviceAPI(
            ec2_client=ec2_client(
                region=region,
                zone=zone,
                access_key_id=access_key_id,
                secret_access_key=secret_access_key,
                validate_region=validate_region,
            ),
            cluster_id=cluster_id,
        )
    except (InvalidRegionError, InvalidZoneError) as e:
        raise StorageInitializationError(
            StorageInitializationError.CONFIGURATION_ERROR, *e.args)
