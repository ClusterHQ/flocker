# -*- test-case-name: flocker.node.agents.functional.test_ebs -*-
# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
An EBS implementation of the ``IBlockDeviceAPI``.
"""

from subprocess import check_output
import threading
import time
import logging
from uuid import UUID

from bitmath import Byte, GiB

from pyrsistent import PRecord, field, pset
from zope.interface import implementer
from boto import ec2
from boto import config
from boto.ec2.connection import EC2Connection
from boto.utils import get_instance_metadata
from boto.exception import EC2ResponseError
from twisted.python.filepath import FilePath

from eliot import Message

from .blockdevice import (
    IBlockDeviceAPI, BlockDeviceVolume, UnknownVolume, AlreadyAttachedVolume,
    UnattachedVolume,
)
from ._logging import (
    AWS_ACTION, BOTO_EC2RESPONSE_ERROR, NO_AVAILABLE_DEVICE,
    NO_NEW_DEVICE_IN_OS, WAITING_FOR_VOLUME_STATUS_CHANGE,
    BOTO_LOG_HEADER, IN_USE_DEVICES,
)

DATASET_ID_LABEL = u'flocker-dataset-id'
METADATA_VERSION_LABEL = u'flocker-metadata-version'
CLUSTER_ID_LABEL = u'flocker-cluster-id'
BOTO_NUM_RETRIES = u'20'
VOLUME_STATE_CHANGE_TIMEOUT = 300
MAX_ATTACH_RETRIES = 3


class EliotLogHandler(logging.Handler):
    _to_log = {"Method", "Path", "Params"}

    def emit(self, record):
        fields = vars(record)
        # Only log certain things.  The log is massively too verbose
        # otherwise.
        if fields.get("msg", ":").split(":")[0] in self._to_log:
            Message.new(
                message_type=BOTO_LOG_HEADER, **fields
            ).write()


def _enable_boto_logging():
    """
    Make boto log activity using Eliot.
    """
    logger = logging.getLogger("boto")
    logger.addHandler(EliotLogHandler())

    # It seems as though basically all boto log messages are at the same
    # level.  Either we can see all of them or we can see none of them.
    # We'll do some extra filtering in the handler.
    logger.setLevel(logging.DEBUG)

_enable_boto_logging()


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
        :param FilePath discovered: The device which was discovered on the
            system.
        """
        self.requested = requested
        self.discovered = discovered

    def __str__(self):
        return self._template.format(
            self.requested.path, self.discovered.path,
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

        # Trace IBlockDeviceAPI ``method`` as Eliot Action.
        # See https://clusterhq.atlassian.net/browse/FLOC-2054
        # for ensuring all method arguments are serializable.
        with AWS_ACTION(operation=[method_name, args, kwargs]):
            try:
                return method(*args, **kwargs)
            except EC2ResponseError as e:
                BOTO_EC2RESPONSE_ERROR(
                    aws_code=e.code,
                    aws_message=e.message,
                    aws_request_id=e.request_id,
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
    return BlockDeviceVolume(
        blockdevice_id=unicode(ebs_volume.id),
        size=int(GiB(ebs_volume.size).to_Byte().value),
        attached_to=ebs_volume.attach_data.instance_id,
        dataset_id=UUID(ebs_volume.tags[DATASET_ID_LABEL])
    )


def _wait_for_volume(volume,
                     start_status,
                     transient_status,
                     end_status):
    """
    Helper function to wait for a given volume to change state
    from ``start_status`` via ``transient_status`` to ``end_status``.

    :param boto.ec2.volume volume: Volume to check
        status for.
    :param unicode start_status: Volume status at starting point.
    :param unicode transient_status: Allowed transient state for
        volume to be in, on the way to ``end_status``.
    :param unicode end_status: Expected destination status for
        the input volume.

    :raises Exception: When input volume failed to reach
        expected destination status.
    """
    # It typically takes a few seconds for anything to happen, so start
    # out sleeping a little before doing initial check to reduce
    # unnecessary polling of the API:
    time.sleep(5.0)

    # Wait ``VOLUME_STATE_CHANGE_TIMEOUT`` seconds for
    # volume status to transition from
    # start_status -> transient_status -> end_status.
    start_time = time.time()
    while time.time() - start_time < VOLUME_STATE_CHANGE_TIMEOUT:
        try:
            volume.update()
        except EC2ResponseError as e:
            # If AWS cannot find the volume, raise ``UnknownVolume``.
            # (http://docs.aws.amazon.com/AWSEC2/latest/APIReference/errors-overview.html
            # for error details).
            if e.code == u'InvalidVolume.NotFound':
                raise UnknownVolume(volume.id)
        if volume.status == end_status:
            return
        elif volume.status not in [start_status, transient_status]:
            break
        time.sleep(1.0)

        WAITING_FOR_VOLUME_STATUS_CHANGE(volume_id=volume.id,
                                         status=volume.status,
                                         target_status=end_status,
                                         wait_time=(time.time() - start_time))

    # We either:
    # 1) Timed out waiting to reach ``end_status``, or,
    # 2) Reached an unexpected status (state change did not
    #    start, or failed).
    # Raise an ``Exception`` in both cases.
    raise Exception(
        'Volume state transition failed. '
        'Volume: {!r}, '
        'Start Status: {!r}, '
        'Transient Status: {!r}, '
        'Expected End Status: {!r}, '
        'Discovered End Status: {!r},'
        'Wait time: {!r},'
        'Time limit: {!r}.'.format(
            volume, start_status, transient_status, end_status,
            volume.status, time.time() - start_time,
            VOLUME_STATE_CHANGE_TIMEOUT
            )
        )


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

        :returns: boto.ec2.volume.Volume for the input id.

        :raise UnknownVolume: If no volume with a matching identifier can be
             found.
        """
        try:
            all_volumes = self.connection.get_all_volumes(
                volume_ids=[blockdevice_id])
        except EC2ResponseError as e:
            # https://docs.aws.amazon.com/AWSEC2/latest/APIReference/errors-overview.html#CommonErrors
            if e.error_code == "InvalidVolume.NotFound":
                raise UnknownVolume(blockdevice_id)
            else:
                raise

        for volume in all_volumes:
            if volume.id == blockdevice_id:
                return volume
        raise UnknownVolume(blockdevice_id)

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
        devices = pset({v.attach_data.device for v in volumes
                       if v.attach_data.instance_id == instance_id})
        devices = devices | devices_in_use
        IN_USE_DEVICES(devices=devices).write()

        for suffix in b"fghijklmonp":
            file_name = u'/dev/sd' + suffix
            if file_name not in devices:
                return file_name

        # Could not find any suitable device that is available
        # for attachment. Log to Eliot before giving up.
        NO_AVAILABLE_DEVICE(devices=devices).write()
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
        _wait_for_volume(requested_volume,
                         start_status=u'',
                         transient_status=u'creating',
                         end_status=u'available')

        # Return created volume in BlockDeviceVolume format.
        return _blockdevicevolume_from_ebs_volume(requested_volume)

    def list_volumes(self):
        """
        Return all volumes that belong to this Flocker cluster.
        """
        volumes = []
        for ebs_volume in self.connection.get_all_volumes():
            if _is_cluster_volume(self.cluster_id, ebs_volume):
                volumes.append(
                    _blockdevicevolume_from_ebs_volume(ebs_volume)
                )
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
        :raises AttachedUnexpectedDevice: If the attach operation fails to
            associate the volume with the expected OS device file.  This
            indicates use on an unsupported OS, a misunderstanding of the EBS
            device assignment rules, or some other bug in this implementation.
        """
        ebs_volume = self._get_ebs_volume(blockdevice_id)
        volume = _blockdevicevolume_from_ebs_volume(ebs_volume)
        if (volume.attached_to is not None or
                ebs_volume.status != 'available'):
            raise AlreadyAttachedVolume(blockdevice_id)

        ignore_devices = pset([])
        attach_attempts = 0
        while True:
            with self.lock:
                # begin lock scope

                blockdevices = FilePath(b"/sys/block").children()
                volumes = self.connection.get_all_volumes()
                device = self._next_device(attach_to, volumes, ignore_devices)

                if device is None:
                    # XXX: Handle lack of free devices in ``/dev/sd[f-p]``.
                    # (https://clusterhq.atlassian.net/browse/FLOC-1887).
                    # No point in attempting an ``attach_volume``, return.
                    return

                try:
                    self.connection.attach_volume(blockdevice_id,
                                                  attach_to,
                                                  device)
                except EC2ResponseError as e:
                    # If attach failed that is often because of eventual
                    # consistency in AWS, so let's ignore this one if it
                    # fails:
                    if e.code == u'InvalidParameterValue':
                        attach_attempts += 1
                        if attach_attempts == MAX_ATTACH_RETRIES:
                            raise
                        ignore_devices = ignore_devices.add(device)
                    else:
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
                        self.detach_volume(blockdevice_id)
                        raise AttachedUnexpectedDevice(device, device_path)
                    break
                # end lock scope

        _wait_for_volume(ebs_volume,
                         start_status=u'available',
                         transient_status=u'attaching',
                         end_status=u'in-use')

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
        ebs_volume = self._get_ebs_volume(blockdevice_id)
        volume = _blockdevicevolume_from_ebs_volume(ebs_volume)
        if (volume.attached_to is None or
                ebs_volume.status != 'in-use'):
            raise UnattachedVolume(blockdevice_id)

        self.connection.detach_volume(blockdevice_id)

        _wait_for_volume(ebs_volume,
                         start_status=u'in-use',
                         transient_status=u'detaching',
                         end_status=u'available')

    def destroy_volume(self, blockdevice_id):
        """
        Destroy EBS volume identified by blockdevice_id.

        :param String blockdevice_id: EBS UUID for volume to be destroyed.

        :raises UnknownVolume: If there does not exist a Flocker cluster
            volume identified by input blockdevice_id.
        :raises Exception: If we failed to destroy Flocker cluster volume
            corresponding to input blockdevice_id.
        """
        ebs_volume = self._get_ebs_volume(blockdevice_id)
        destroy_result = self.connection.delete_volume(blockdevice_id)
        if destroy_result:
            try:
                _wait_for_volume(ebs_volume,
                                 start_status=u'available',
                                 transient_status=u'deleting',
                                 end_status='')
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
        if volume.attached_to is None:
            raise UnattachedVolume(blockdevice_id)

        compute_instance_id = self.compute_instance_id()
        if volume.attached_to != compute_instance_id:
            # This is untested.  See FLOC-2453.
            raise Exception(
                "Volume is attached to {}, not to {}".format(
                    volume.attached_to, compute_instance_id
                )
            )

        return _expected_device(ebs_volume.attach_data.device)


def aws_from_configuration(region, zone, access_key_id, secret_access_key,
                           cluster_id):
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

    :return: A ``EBSBlockDeviceAPI`` instance using the given parameters.
    """
    return EBSBlockDeviceAPI(
        ec2_client=ec2_client(
            region=region,
            zone=zone,
            access_key_id=access_key_id,
            secret_access_key=secret_access_key,
        ),
        cluster_id=cluster_id,
    )
