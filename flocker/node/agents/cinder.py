# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
A Cinder implementation of the ``IBlockDeviceAPI``.
"""
from uuid import UUID

from bitmath import Byte, GB, TB

from keystoneclient_rackspace.v2_0 import RackspaceAuth
from keystoneclient.session import Session

from cinderclient.client import Client

from zope.interface import implementer, Interface

from .blockdevice import IBlockDeviceAPI, BlockDeviceVolume

# Rackspace public docs say "The minimum size for a Cloud Block Storage volume
# is 50 GB for an SSD volume or 75GB for an SATA volume. The maximum volume
# size is 1TB."
# * http://www.rackspace.com/knowledge_center/product-faq/cloud-block-storage
# Rackspace API agrees "u'{"badRequest": {"message": "Invalid input
# received: \'size\' parameter must be between 75 and 1024", "code":
# 400}}'"
# Let's assume that we only support SATA volumes for now.
# Eventually we'll validate size at configuration time based on backend limits.
# See https://clusterhq.atlassian.net/browse/FLOC-1579
RACKSPACE_MINIMUM_BLOCK_SIZE = int(GB(75).to_Byte().value)
RACKSPACE_MAXIMUM_BLOCK_SIZE = int(TB(1).to_Byte().value)

# The key name used for identifying the Flocker cluster_id in the metadata for
# a volume.
CLUSTER_ID_LABEL = u'flocker-cluster-id'

# The key name used for identifying the Flocker dataset_id in the metadata for
# a volume.
DATASET_ID_LABEL = u'flocker-dataset-id'


class ICinderVolumeManager(Interface):
    """
    The parts of ``cinderclient.v2.volumes.VolumeManager`` that we use.
    """
    def create(size, metadata=None):
        """
        Create a new cinder volume and return a representation of that volume.
        """

    def list():
        """
        Return a list of all the cinder volumes known to this client; limited
        by the access granted for a particular API key and the region.
        """

    def set_metadata(volume, metadata):
        """
        Set the metadata for a cinder volume.
        """


def wait_for_volume(client, new_volume):
    """
    Wait for a volume with the same id as ``new_volume`` to be listed as
    ``available`` and return that listed volume.
    """
    while True:
        for listed_volume in client.volumes.list():
            if listed_volume.id == new_volume.id:
                if listed_volume.status == 'available':
                    return listed_volume


@implementer(IBlockDeviceAPI)
class CinderBlockDeviceAPI(object):
    """
    A cinder implementation of ``IBlockDeviceAPI`` which creates block devices
    in an OpenStack cluster.
    """
    def __init__(self, cinder_client, cluster_id):
        """
        :param ICinderVolumeManager cinder_client: A client for interacting
            with Cinder API.
        :param UUID cluster_id: An ID that will be included in the names of
            Cinder block devices in order to associate them with a particular
            Flocker cluster.
        """
        self.cinder_client = cinder_client
        self.cluster_id = cluster_id

    def create_volume(self, dataset_id, size):
        """
        Create a block device using the cinder VolumeManager.
        Store the cluster_id and dataset_id as metadata.

        http://docs.rackspace.com/cbs/api/v1.0/cbs-devguide/content/POST_createVolume_v1__tenant_id__volumes_volumes.html

        Discussion:
         * Assign a Human readable name and description?

         * pyrax.volume.create expects a size in GB
           The minimum SATA disk size on Rackspace is 100GB.
           How do we enforce that?
           And what (if any) errors should we raise if the user requests something smaller?
           Is this an OpenStack limit or something specific to Rackspace?

         * Rackspace will assign its own unique ID to the volume.
           Should that be the value of ``BlockDeviceVolume.blockdevice_id`` ?
           That field type is unicode rather than UUID which was (I think) chosen so as to support provider specific volume ID strings.
        """
        metadata = {
            CLUSTER_ID_LABEL: unicode(self.cluster_id),
            DATASET_ID_LABEL: unicode(dataset_id),
        }
        # We supply metadata here and it'll be included in the returned cinder
        # volume record, but it'll be lost by Rackspace, so...
        requested_volume = self.cinder_client.volumes.create(
            size=Byte(size).to_GB().value,
            metadata=metadata,
        )
        created_volume = wait_for_volume(self.cinder_client, requested_volume)
        # So once the volume has actually been created, we set the metadata
        # again. One day we hope this won't be necessary.
        # See Rackspace support ticket: 150422-ord-0000495'
        self.cinder_client.volumes.set_metadata(
            created_volume, metadata
        )
        # Use requested volume here, because it has the desired metadata.
        return _blockdevicevolume_from_cinder_volume(requested_volume)

    def list_volumes(self):
        """
        Return ``BlockDeviceVolume`` instances for all the Cinder devices that have the expected ``cluster_id`` among the metadata.

        http://docs.rackspace.com/cbs/api/v1.0/cbs-devguide/content/GET_getVolumesDetail_v1__tenant_id__volumes_detail_volumes.html
        """
        volumes = []
        for cinder_volume in self.cinder_client.volumes.list():
            if _is_cluster_volume(self.cluster_id, cinder_volume):
                volumes.append(
                    _blockdevicevolume_from_cinder_volume(cinder_volume)
                )
        return volumes

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


def _is_cluster_volume(cluster_id, cinder_volume):
    """
    :return: ``True`` if ``cinder_volume`` metadata has a
    ``CLUSTER_ID_LABEL`` value matching ``cluster_id`` else ``False``.
    """
    actual_cluster_id = cinder_volume.metadata.get(CLUSTER_ID_LABEL)
    if actual_cluster_id == cluster_id:
        return True
    return False


def _blockdevicevolume_from_cinder_volume(cinder_volume):
    """
    :param CloudBlockStorageVolume cinder_volume:
    :returns: A ``BlockDeviceVolume`` based on values found in the supplied
        instance.
    """
    return BlockDeviceVolume(
        blockdevice_id=unicode(cinder_volume.id),
        size=int(GB(cinder_volume.size).to_Byte().value),
        host=None,
        dataset_id=UUID(cinder_volume.metadata[DATASET_ID_LABEL])
    )


def authenticated_cinder_client(username, api_key, region):
    """
    XXX: This is currently RackSpace specific.

    :param unicode username: A RackSpace API username.
    :param unicode api_key: A RackSpace API key.
    :param unicode region: A RackSpace region slug.
    :return: A ``cinder.client.Client`` instance with a ``volumes`` attribute
        that conforms to ``ICinderVolumeManager``.
    """
    auth_url = "https://identity.api.rackspacecloud.com/v2.0"
    auth = RackspaceAuth(auth_url=auth_url, username=username, api_key=api_key)
    session = Session(auth=auth)
    return Client(version=1, session=session, region_name=region)


def cinder_api(cinder_client, cluster_id):
    """
    """
    return CinderBlockDeviceAPI(cinder_client, cluster_id)
