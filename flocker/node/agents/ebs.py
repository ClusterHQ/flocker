# -*- test-case-name: flocker.node.agents.functional.test_ebs -*-
# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
An EBS implementation of the ``IBlockDeviceAPI``.
"""

from subprocess import check_output
import threading
import time
from uuid import UUID

from bitmath import Byte, GiB

from pyrsistent import PRecord, field
from zope.interface import implementer
from boto import ec2
from boto import config
from boto.ec2.connection import EC2Connection
from boto.utils import get_instance_metadata
from boto.exception import EC2ResponseError
from twisted.python.filepath import FilePath
from eliot import Field, MessageType

from .blockdevice import (
    IBlockDeviceAPI, BlockDeviceVolume, UnknownVolume, AlreadyAttachedVolume,
    UnattachedVolume, get_blockdevice_volume,
)

DATASET_ID_LABEL = u'flocker-dataset-id'
METADATA_VERSION_LABEL = u'flocker-metadata-version'
CLUSTER_ID_LABEL = u'flocker-cluster-id'
ATTACHED_DEVICE_LABEL = u'attached-device-name'
BOTO_NUM_RETRIES = u'10'

# Set Boto debug level to ``1``, requesting basic debug messages from Boto
# to be printed.
# See https://code.google.com/p/boto/wiki/BotoConfig#Boto
# for available debug levels.
# Warning: BotoConfig is a Boto global option, so, all Boto clients from
# from this process will have their log levels modified. See
# https://clusterhq.atlassian.net/browse/FLOC-1962
# to track evaluation of impact of log level change.
BOTO_DEBUG_LEVEL = u'1'

# Begin: Scaffolding for logging Boto client and server exceptions
# via Eliot.
CODE = Field.for_types(
    "code", [bytes, unicode],
    u"The error response code.")
MESSAGE = Field.for_types(
    "message", [bytes, unicode],
    u"A human-readable error message given by the response.",
)
REQUEST_ID = Field.for_types(
    "request_id", [bytes, unicode],
    u"The unique identifier assigned by the server for this request.",
)

# Log boto.exception.BotoEC2ResponseError, covering all errors from AWS:
# server operation rate limit exceeded, invalid server request parameters, etc.
BOTO_EC2RESPONSE_ERROR = MessageType(
    u"boto:boto_ec2response_error", [
        CODE,
        MESSAGE,
        REQUEST_ID,
    ],
)
# End: Scaffolding for logging Boto errors.


def ec2_client(region, zone, access_key_id, secret_access_key):
    """
    Establish connection to EC2 client.

    :param str region: The name of the EC2 region to connect to.
    :param str zone: The zone for the EC2 region to connect to.
    :param str access_key_id: "aws_access_key_id" credential for EC2.
    :param str secret_access_key: "aws_secret_access_key" EC2 credential.

    :return: An ``_EC2`` giving information about EC2 client connection
        and EC2 instance zone.
    """

    # Set 2 retry knobs in Boto to BOTO_NUM_RETRIES:
    # 1. ``num_retries``:
    # Request automatic exponential backoff and retry
    # attempts by Boto if an EC2 API call fails with
    # ``RequestLimitExceeded`` due to system load.
    # 2. ``metadata_service_num_attempts``:
    # Request for retry attempts by Boto to
    # retrieve data from Metadata Service used to retrieve
    # credentials for IAM roles on EC2 instances.
    if not config.has_section('Boto'):
        config.add_section('Boto')
    config.set('Boto', 'num_retries', BOTO_NUM_RETRIES)
    config.set('Boto', 'metadata_service_num_attempts', BOTO_NUM_RETRIES)

    # Set Boto debug level to BOTO_DEBUG_LEVEL:
    # ``1``: log basic debug messages
    config.set('Boto', 'debug', BOTO_DEBUG_LEVEL)

    # Get Boto EC2 connection with ``EC2ResponseError`` logged by Eliot.
    connection = ec2.connect_to_region(region,
                                       aws_access_key_id=access_key_id,
                                       aws_secret_access_key=secret_access_key)
    return _EC2(zone=zone,
                connection=_LoggedBotoConnection(connection=connection))


def _boto_logged_method(method_name, original_name):
    """
    Run a boto.ec2.connection.EC2Connection method and
    log additional information about any exceptions that are raised.

    :param str method_name: The name of the method of the wrapped object to
        call.
    :param str original_name: The name of the attribute of self where the
        wrapped object can be found.

    :return: A function which will call the method of the wrapped object and do
        the extra exception logging.
    """
    def _run_with_logging(self, *args, **kwargs):
        """
        Run given boto.ec2.connection.EC2Connection method with exception
        logging for ``EC2ResponseError``.
        """
        original = getattr(self, original_name)
        method = getattr(original, method_name)
        try:
            return method(*args, **kwargs)
        except EC2ResponseError as e:
            BOTO_EC2RESPONSE_ERROR(
                code=e.code,
                message=e.message,
                request_id=e.request_id,
            ).write()
            raise
    return _run_with_logging


def boto_logger(*args, **kwargs):
    """
    Decorator to log all callable boto.ec2.connection.EC2Connection
    methods.

    :return: A function that will decorate all methods of the given
        class with Boto exception logging.
    """
    def _class_decorator(cls):
        for attr in EC2Connection.__dict__:
            # Log wrap all callable methods except `__init__`.
            if attr != '__init__':
                attribute = getattr(EC2Connection, attr)
                if callable(attribute):
                    setattr(cls, attr,
                            _boto_logged_method(attr, *args, **kwargs))
        return cls
    return _class_decorator


@boto_logger("connection")
class _LoggedBotoConnection(PRecord):
    """
    Wrapper ``PRecord`` around ``boto.ec2.connection.EC2Connection``
    to facilitate logging of exceptions from Boto APIs.

    :ivar boto.ec2.connection.EC2Connection connection: Object
        representing connection to an EC2 instance with logged
        ``EC2ConnectionError``.
    """
    connection = field(mandatory=True)


class _EC2(PRecord):
    """
    :ivar str zone: The name of the zone for the connection.
    :ivar boto.ec2.connection.EC2Connection connection: Object
        representing connection to an EC2 instance.
    """
    zone = field(mandatory=True)
    connection = field(mandatory=True)


def _blockdevicevolume_from_ebs_volume(ebs_volume):
    """
    Helper function to convert Volume information from
    EBS format to Flocker block device format.

    :param boto.ec2.volume ebs_volume: Volume in EC2 format.

    :return: Input volume in BlockDeviceVolume format.
    """
    ebs_volume.update()
    return BlockDeviceVolume(
        blockdevice_id=unicode(ebs_volume.id),
        size=int(GiB(ebs_volume.size).to_Byte().value),
        attached_to=ebs_volume.attach_data.instance_id,
        dataset_id=UUID(ebs_volume.tags[DATASET_ID_LABEL])
    )


def _wait_for_volume(expected_volume,
                     expected_status=u'available',
                     time_limit=60):
    """
    Helper function to wait for up to 60s for given volume
    to be in 'available' state.

    :param boto.ec2.volume expected_volume: Volume to check
        status for.
    :param str expected_status: Target state of the input
        volume. Default target state is ''available''.
    :param int time_limit: Upper bound of wait time for input
        volume to reach expected state. Defaults to 60 seconds.

    :raises Exception: When input volume did not reach
        expected state within time limit.
    """
    start_time = time.time()
    expected_volume.update()
    while expected_volume.status != expected_status:
        elapsed_time = time.time() - start_time
        if elapsed_time < time_limit:
            time.sleep(0.1)
            expected_volume.update()
        else:
            raise Exception(
                'Timed out while waiting for volume. '
                'Expected Volume: {!r}, '
                'Expected Status: {!r}, '
                'Actual Status: {!r}, '
                'Elapsed Time: {!r}, '
                'Time Limit: {!r}.'.format(
                    expected_volume, expected_status,
                    expected_volume.status, elapsed_time,
                    time_limit
                )
            )


def _check_blockdevice_size(device, size):
    """
    Helper function to check if the size of block device with given
    suffix matches the input size.

    :param unicode device: Name of the block device to check for size.
    :param int size: Size, in SI metric bytes, of device we are interested in.

    :returns: True if a block device with given name has given size.
        False otherwise.
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

    return size == device_size


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

    :returns: formatted string name of the new block device.
    :rtype: unicode
    """
    start_time = time.time()
    elapsed_time = time.time() - start_time
    while elapsed_time < time_limit:
        for device in list(set(FilePath(b"/sys/block").children()) -
                           set(base)):
            device_name = FilePath.basename(device)
            if (device_name.startswith((b"sd", b"xvd")) and
                    _check_blockdevice_size(device_name, size)):
                new_device = u'/dev/' + device_name.decode("ascii")
                return new_device
        time.sleep(0.1)
        elapsed_time = time.time() - start_time
    return None


def _is_cluster_volume(cluster_id, ebs_volume):
    """
    Helper function to check if given volume belongs to
    given cluster.

    :param UUID cluster_id: UUID of Flocker cluster to check for
        membership.
    :param boto.ec2.volume ebs_volume: EBS volume to check for
        input cluster membership.

    :return bool: True if input volume belongs to input
        Flocker cluster. False otherwise.
    """
    actual_cluster_id = ebs_volume.tags.get(CLUSTER_ID_LABEL)
    if actual_cluster_id is not None:
        actual_cluster_id = UUID(actual_cluster_id)
        if actual_cluster_id == cluster_id:
            return True
    return False


@implementer(IBlockDeviceAPI)
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

    def compute_instance_id(self):
        """
        Look up the EC2 instance ID for this node.
        """
        return get_instance_metadata()['instance-id'].decode("ascii")

    def _get_ebs_volume(self, blockdevice_id):
        """
        Lookup EBS Volume information for a given blockdevice_id.

        :param unicode blockdevice_id: ID of a blockdevice that needs lookup.

        :returns boto.ec2.volume.Volume for the input id. ``None`` if
            no boto.ec2.volume.Volume was found for the given id.
        """
        for volume in self.connection.get_all_volumes(
                volume_ids=[blockdevice_id]):
            if volume.id == blockdevice_id:
                # Sync volume for uptodate metadata
                volume.update()
                return volume
        return None

    def _next_device(self, instance_id):
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

        :returns unicode file_name: available device name for attaching
            EBS volume.
        :returns ``None`` if suitable EBS device names on this EC2
            instance are currently occupied.
        """
        volumes = self.connection.get_all_volumes()
        devices = [v.attach_data.device for v in volumes
                   if v.attach_data.instance_id == instance_id]
        for suffix in b"fghijklmonp":
            file_name = u'/dev/sd' + suffix
            if file_name not in devices:
                return file_name
        return None

    def create_volume(self, dataset_id, size):
        """
        Create a volume on EBS. Store Flocker-specific
        {metadata version, cluster id, dataset id} for the volume
        as volume tag data.
        Open issues: https://clusterhq.atlassian.net/browse/FLOC-1792
        """
        requested_volume = self.connection.create_volume(
            size=int(Byte(size).to_GiB().value), zone=self.zone)

        # Stamp created volume with Flocker-specific tags.
        metadata = {
            METADATA_VERSION_LABEL: '1',
            CLUSTER_ID_LABEL: unicode(self.cluster_id),
            DATASET_ID_LABEL: unicode(dataset_id),
        }
        self.connection.create_tags([requested_volume.id],
                                    metadata)

        # Wait for created volume to reach 'available' state.
        _wait_for_volume(requested_volume)

        # Return created volume in BlockDeviceVolume format.
        return _blockdevicevolume_from_ebs_volume(requested_volume)

    def list_volumes(self):
        """
        Return all volumes in {available, in-use} state that belong to
        this Flocker cluster.
        """
        volumes = []
        for ebs_volume in self.connection.get_all_volumes():
            if ((_is_cluster_volume(self.cluster_id, ebs_volume)) and
               (ebs_volume.status in [u'available', u'in-use'])):
                volumes.append(
                    _blockdevicevolume_from_ebs_volume(ebs_volume)
                )
        return volumes

    def resize_volume(self, blockdevice_id, size):
        pass

    # cloud_instance_id here too
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
        """
        volume = get_blockdevice_volume(self, blockdevice_id)
        if volume.attached_to is not None:
            raise AlreadyAttachedVolume(blockdevice_id)

        with self.lock:
            # begin lock scope

            blockdevices = FilePath(b"/sys/block").children()
            device = self._next_device(attach_to)

            if device is None:
                # XXX: Handle lack of free devices in ``/dev/sd[f-p]`` range
                # (see https://clusterhq.atlassian.net/browse/FLOC-1887).
                # No point in attempting an ``attach_volume``, so, return.
                return

            self.connection.attach_volume(blockdevice_id, attach_to, device)

            # Wait for new device to manifest in the OS. Since there
            # is currently no standardized protocol across Linux guests
            # in EC2 for mapping `device` to the name device driver picked (see
            # http://docs.aws.amazon.com/AWSEC2/latest/UserGuide/device_naming.html),
            # let us wait for a new block device to be available to the OS,
            # and interpret it as ours.
            # Wait under lock scope to reduce false positives.
            new_device = _wait_for_new_device(blockdevices, volume.size)

            # end lock scope

        # Stamp EBS volume with attached device name tag.
        # If OS fails to see new block device in 60 seconds,
        # `new_device` is `None`, indicating the volume failed
        # to attach to the compute instance.
        ebs_volume = self._get_ebs_volume(blockdevice_id)
        metadata = {
            ATTACHED_DEVICE_LABEL: unicode(new_device),
        }
        if new_device is not None:
            self.connection.create_tags([ebs_volume.id], metadata)
        _wait_for_volume(ebs_volume, expected_status=u'in-use')

        attached_volume = volume.set('attached_to', attach_to)
        return attached_volume

    def detach_volume(self, blockdevice_id):
        """
        Detach EBS volume identified by blockdevice_id.

        :param unicode blockdevice_id: EBS UUID for volume to be detached.

        :raises UnknownVolume: If there does not exist a BlockDeviceVolume
            corresponding to the input blockdevice_id.
        :raises UnattachedVolume: If the BlockDeviceVolume for the
            blockdevice_id is not currently 'in-use'.
        """
        volume = get_blockdevice_volume(self, blockdevice_id)
        if volume.attached_to is None:
            raise UnattachedVolume(blockdevice_id)

        self.connection.detach_volume(blockdevice_id)
        ebs_volume = self._get_ebs_volume(blockdevice_id)
        _wait_for_volume(ebs_volume, expected_status=u'available',
                         time_limit=180)

        # Delete attached device metadata from EBS Volume
        self.connection.delete_tags([ebs_volume.id], [ATTACHED_DEVICE_LABEL])

    def destroy_volume(self, blockdevice_id):
        """
        Destroy EBS volume identified by blockdevice_id.

        :param String blockdevice_id: EBS UUID for volume to be destroyed.

        :raises UnknownVolume: If there does not exist a Flocker cluster
            volume identified by input blockdevice_id.
        :raises Exception: If we failed to destroy Flocker cluster volume
            corresponding to input blockdevice_id.
        """
        for volume in self.list_volumes():
            if volume.blockdevice_id == blockdevice_id:
                ret_val = self.connection.delete_volume(blockdevice_id)
                if ret_val is False:
                    raise Exception(
                        'Failed to delete volume: {!r}'.format(blockdevice_id)
                    )
                else:
                    return
        raise UnknownVolume(blockdevice_id)

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
        volume = get_blockdevice_volume(self, blockdevice_id)
        if volume.attached_to is None:
            raise UnattachedVolume(blockdevice_id)

        ebs_volume = self._get_ebs_volume(blockdevice_id)
        try:
            device = ebs_volume.tags[ATTACHED_DEVICE_LABEL]
        except KeyError:
            raise UnattachedVolume(blockdevice_id)
        if device is None:
            raise UnattachedVolume(blockdevice_id)
        return FilePath(device)
