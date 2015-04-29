# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
An EBS implementation of the ``IBlockDeviceAPI``.
"""

from bitmath import Byte, GB
import time
from uuid import UUID

from boto import ec2
from pyrsistent import PRecord, field
from zope.interface import implementer

from .blockdevice import IBlockDeviceAPI, BlockDeviceVolume, UnknownVolume

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
    """
    return BlockDeviceVolume(
        blockdevice_id=unicode(ebs_volume.id),
        size=int(GB(ebs_volume.size).to_Byte().value),
        host=None,
        dataset_id=UUID(ebs_volume.tags[DATASET_ID_LABEL])
    )


def _wait_for_volume(expected_volume,
                     expected_status=u'available',
                     time_limit=60):
    """
    Helper function to wait for up to 60s for given volume
    to be in 'available' state.
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

        :param ``_EC2`` ec2_client: A record of EC2 connection and zone.
        :param String cluster_id: UUID of cluster for this
            API instance.
        """
        self.connection = ec2_client.connection
        self.zone = ec2_client.zone
        self.cluster_id = cluster_id

    def _blockdevicevolume_from_ebs_volume(self, ebs_volume):
        """
        Helper function to convert Volume information from
        EBS format to Flocker block device format.
        """
        return BlockDeviceVolume(
            blockdevice_id=unicode(ebs_volume.id),
            size=int(GB(ebs_volume.size).to_Byte().value),
            host=None,
            dataset_id=UUID(ebs_volume.tags[DATASET_ID_LABEL])
        )

    def create_volume(self, dataset_id, size):
        """
        Create a volume on EBS. Store Flocker-specific
        {metadata version, cluster id, dataset id} for the volume
        as volume tag data.

        :param String dataset_id: Dataset_id for the volume.
        :param int size: Requested volume size in Bytes.

        :return BlockDeviceVolume volume: Created volume in
            BlockDeviceVolume format.
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

    def attach_volume(self, blockdevice_id, host):
        pass

    def detach_volume(self, blockdevice_id):
        pass

    def destroy_volume(self, blockdevice_id):
        """
        Destroy EBS volume identified by blockdevice_id.

        :param String blockdevice_id: EBS UUID for volume to be destroyed.

        :raises UnknownVolume: If there does not exist a Flocker cluster
            volume identified by input blockdevice_id.
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
        pass
