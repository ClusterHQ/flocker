# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
An EBS implementation of the ``IBlockDeviceAPI``.
"""

from uuid import UUID
from bitmath import Byte, GB
from boto import ec2

from pyrsistent import PRecord, field

from zope.interface import implementer

from .blockdevice import IBlockDeviceAPI, BlockDeviceVolume

def ec2_client(zone, access_key_id, secret_access_key):
    ec2_zones = boto.ec2.get_all_zones([zone])
    region = ec2_zones[0].region_name
    return _EC2(zone=zone,
                connection=ec2.connect_to_region(region,
                    aws_access_key_id=access_key_id,
                    aws_secret_access_key=secret_access_key))


class _EC2(PRecord):
    """
    """
    zone = field()
    connection = field()


@implementer(IBlockDeviceAPI)
class EBSBlockDeviceAPI(object):
    """
    An EBS implementation of ``IBlockDeviceAPI`` which creates
    block devices in an EC2 cluster using Boto APIs.
    """
    def __init__(self, ec2_client, cluster_id):
        self.connection = ec2_client.connection
        self.zone = ec2_client.zone
        self.cluster_id = cluster_id


    def _blockdevicevolume_from_ebs_volume(ebs_volume):
        """
        """
        return BlockDeviceVolume(
            blockdevice_id=unicode(ebs_volume.id),
            size=int(GB(ebs_volume.size).to_Byte().value),
            host=None,
            dataset_id=UUID(ebs_volume.tags[DATASET_ID_LABEL])
        )


    def create_volume(self, dataset_id, size):
        """
        """
        metadata = {
            METADATA_VERSION_LABEL: '1',
            DATASET_ID_LABEL: unicode(dataset_id),
        }
        requested_volume = self.connection.create_volume(
            size=Byte(size).to_GB().value, self.zone)
        self.connection.create_tags([requested_volume.id],
                                    metadata)
        requested_volume.update()
        return _blockdevicevolume_from_ebs_volume(requested_volume)


    def list_volumes(self):
        """
        """
        pass

    def resize_volume(self, blockdevice_id, size):
        pass

    def attach_volume(self, blockdevice_id, host):
        pass

    def detach_volume(self, blockdevice_id):
        pass

    def destroy_volume(self, blockdevice_id):
        pass

    def get_device_path(self, blockdevice_id):
        pass
