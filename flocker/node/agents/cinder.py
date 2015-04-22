# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
A Cinder implementation of the ``IBlockDeviceAPI``.
"""

from keystoneclient_rackspace.v2_0 import RackspaceAuth
from keystoneclient.session import Session

from cinderclient.client import Client

from zope.interface import implementer

from .blockdevice import IBlockDeviceAPI


# The key name used for identifying the Flocker cluster_id in the metadata for
# a volume.
CLUSTER_ID_LABEL = u'flocker-cluster-id'

# The key name used for identifying the Flocker dataset_id in the metadata for
# a volume.
DATASET_ID_LABEL = u'flocker-dataset-id'

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
                else:
                    print "STATUS", listed_volume.status
                    print "METADATA", listed_volume.metadata


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
        Create the block device using the volume_driver.
        Store the dataset_id as metadata
        Store the cluster_id as metadata
        Assign a Human readable name and description?

        http://docs.rackspace.com/cbs/api/v1.0/cbs-devguide/content/POST_createVolume_v1__tenant_id__volumes_volumes.html

        Discussion:
         * Rackspace (maybe cinder in general) supports a block device type, eg SSD or SATA.
           I guess we'll hardcode SATA here to start with
           Maybe expand the API later to make the disk type configurable?

         * pyrax.volume.create expects a size in GB
           The minimum SATA disk size on Rackspace is 100GB.
           How do we enforce that?
           And what (if any) errors should we raise if the user requests something smaller?
           Is this an OpenStack limit or something specific to Rackspace?

         * Rackspace will assign its own unique ID to the volume.
           Should that be the value of ``BlockDeviceVolume.blockdevice_id`` ?
           That field type is unicode rather than UUID which was (I think) chosen so as to support provider specific volume ID strings.
        """
        requested_volume = self.cinder_client.volumes.create(size=100)
        created_volume = wait_for_volume(self.cinder_client, requested_volume)
        import pdb; pdb.set_trace()
        metadata = {
            CLUSTER_ID_LABEL: unicode(self.cluster_id),
            DATASET_ID_LABEL: unicode(dataset_id),
        }
        updated_volume = self.cinder_client.volumes.set_metadata(
            created_volume, metadata
        )
        return _blockdevicevolume_from_cinder_volume(updated_volume)

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
    return cinder_volume


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
