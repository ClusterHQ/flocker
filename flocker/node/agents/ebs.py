# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
An EBS implementation of the ``IBlockDeviceAPI``.
"""

import time
from uuid import UUID
from bitmath import Byte, GB
from boto import ec2

from pyrsistent import PRecord, field

from zope.interface import implementer

from .blockdevice import IBlockDeviceAPI, BlockDeviceVolume, UnknownVolume

DATASET_ID_LABEL = u'flocker-dataset-id'
METADATA_VERSION_LABEL = u'flocker-metadata-version'
CLUSTER_ID_LABEL = u'flocker-cluster-id'


def ec2_client(region, zone, access_key_id, secret_access_key):
    return _EC2(zone=zone,
                connection=ec2.connect_to_region(
                    region,
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

    def _blockdevicevolume_from_ebs_volume(self, ebs_volume):
        """
        """
        return BlockDeviceVolume(
            blockdevice_id=unicode(ebs_volume.id),
            size=int(GB(ebs_volume.size).to_Byte().value),
            host=None,
            dataset_id=UUID(ebs_volume.tags[DATASET_ID_LABEL])
        )

    def _wait_for_volume(self, expected_volume,
                         expected_status=u'available',
                         time_limit=60):
        """
        Wait for up to 60s for volume creation to complete.
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

    def _is_cluster_volume(self, cluster_id, ebs_volume):
        """
        """
        actual_cluster_id = ebs_volume.tags.get(CLUSTER_ID_LABEL)
        if actual_cluster_id is not None:
            actual_cluster_id = UUID(actual_cluster_id)
            if actual_cluster_id == cluster_id:
                return True
        return False

    def create_volume(self, dataset_id, size):
        """
        """
        metadata = {
            METADATA_VERSION_LABEL: '1',
            CLUSTER_ID_LABEL: unicode(self.cluster_id),
            DATASET_ID_LABEL: unicode(dataset_id),
        }
        requested_volume = self.connection.create_volume(
            size=int(Byte(size).to_GB().value), zone=self.zone)
        self.connection.create_tags([requested_volume.id],
                                    metadata)

        self._wait_for_volume(requested_volume)

        return self._blockdevicevolume_from_ebs_volume(requested_volume)

    def list_volumes(self):
        """
        """
        volumes = []
        for ebs_volume in self.connection.get_all_volumes():
            if ((self._is_cluster_volume(self.cluster_id, ebs_volume)) and
               (ebs_volume.status in [u'available', u'in-use'])):
                volumes.append(
                    self._blockdevicevolume_from_ebs_volume(ebs_volume)
                )
        return volumes

    def resize_volume(self, blockdevice_id, size):
        pass

    def attach_volume(self, blockdevice_id, host):
        pass

    def detach_volume(self, blockdevice_id):
        pass

    def destroy_volume(self, blockdevice_id):
        for volume in self.list_volumes():
            if volume.blockdevice_id == blockdevice_id:
                ret_val = self.connection.delete_volume(blockdevice_id)
                if ret_val is False:
                    raise Exception(
                        'Failed to delete volume: {!r}'.format(blockdevice_id)
                    )
                else:
                    return
        raise UnknownVolume(format(blockdevice_id))

    def get_device_path(self, blockdevice_id):
        pass
