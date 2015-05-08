# -*- test-case-name: flocker.node.agents.functional.test_ebs -*-
# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
An EBS implementation of the ``IBlockDeviceAPI``.
"""

import threading
import time
from uuid import UUID

from bitmath import Byte, GB

from pyrsistent import PRecord, field
from zope.interface import implementer
from boto import ec2
from boto.utils import get_instance_metadata

from .blockdevice import (
    IBlockDeviceAPI, BlockDeviceVolume, UnknownVolume, AlreadyAttachedVolume,
    UnattachedVolume
)

DATASET_ID_LABEL = u'flocker-dataset-id'
METADATA_VERSION_LABEL = u'flocker-metadata-version'
CLUSTER_ID_LABEL = u'flocker-cluster-id'


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
    return _EC2(zone=zone,
                connection=ec2.connect_to_region(
                    region,
                    aws_access_key_id=access_key_id,
                    aws_secret_access_key=secret_access_key))


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
        size=int(GB(ebs_volume.size).to_Byte().value),
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

    def compute_instance_id(self):
        """
        Look up the EC2 instance ID for this node.
        """
        return get_instance_metadata()['instance-id'].decode("ascii")

    def _get(self, blockdevice_id):
        """
        Lookup BlockDeviceVolume for given blockdevice_id.

        :param unicode blockdevice_id: ID of a blockdevice that needs lookup.

        :returns BlockDeviceVolume for the given input id.
        """
        for volume in self.list_volumes():
            if volume.blockdevice_id == blockdevice_id:
                return volume
        raise UnknownVolume(blockdevice_id)

    def _get_ebs_volume(self, blockdevice_id):
        """
        Lookup EBS Volume information for a given blockdevice_id.

        :param unicode blockdevice_id: ID of a blockdevice that needs lookup.
        :returns boto.ec2.volume.Volume for the input id.
        """
        for volume in self.connection.get_all_volumes():
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

        :param unicode instance_id: EC2 instance ID.

        :returns unicode file_name: available device name for attaching
            EBS volume.
        """
        volumes = self.connection.get_all_volumes()
        devices = [v.attach_data.device for v in volumes
                   if v.attach_data.instance_id == instance_id]
        for prefix in ['f', 'g', 'h', 'i', 'j', 'k', 'l', 'm', 'n', 'o', 'p']:
            file_name = u'/dev/sd%c' % prefix
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
            size=int(Byte(size).to_GB().value), zone=self.zone)

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
        volume = self._get(blockdevice_id)
        if volume.attached_to is not None:
            raise AlreadyAttachedVolume(blockdevice_id)

        self.lock.acquire()
        device = self._next_device(attach_to)
        self.connection.attach_volume(blockdevice_id, attach_to, device)
        self.lock.release()

        ebs_volume = self._get_ebs_volume(blockdevice_id)
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
        volume = self._get(blockdevice_id)
        if volume.attached_to is None:
            raise UnattachedVolume(blockdevice_id)

        self.connection.detach_volume(blockdevice_id)
        ebs_volume = self._get_ebs_volume(blockdevice_id)
        _wait_for_volume(ebs_volume, expected_status=u'available')

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
        """
