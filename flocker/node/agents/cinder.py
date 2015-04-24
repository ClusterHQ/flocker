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
    The parts of ``cinderclient.v1.volumes.VolumeManager`` that we use.
    See: https://github.com/openstack/python-cinderclient/blob/master/cinderclient/v1/volumes.py#L135 # noqa
    """
    def create(size, metadata=None):
        """
        Creates a volume.

        :param size: Size of volume in GB
        :param metadata: Optional metadata to set on volume creation
        :rtype: :class:`Volume`
        """

    def list():
        """
        Lists all volumes.

        :rtype: list of :class:`Volume`
        """

    def set_metadata(volume, metadata):
        """
        Update/Set a volumes metadata.

        :param volume: The :class:`Volume`.
        :param metadata: A list of keys to be set.
        """


def wait_for_volume(volume_manager, expected_volume):
    """
    Wait for a ``Volume`` with the same ``id`` as ``expected_volume`` to be
    listed and to have a ``status`` value of ``available``.

    :param ICinderVolumeManager volume_manager: An API for listing volumes.
    :param Volume expected_volume: The ``Volume`` to wait for.
    :returns: The listed ``Volume`` that matches ``new_volume``.
    """
    while True:
        for listed_volume in volume_manager.list():
            if listed_volume.id == expected_volume.id:
                if listed_volume.status == 'available':
                    return listed_volume


@implementer(IBlockDeviceAPI)
class CinderBlockDeviceAPI(object):
    """
    A cinder implementation of ``IBlockDeviceAPI`` which creates block devices
    in an OpenStack cluster using Cinder APIs.
    """
    def __init__(self, volume_manager, cluster_id):
        """
        :param ICinderVolumeManager volume_manager: A client for interacting
            with Cinder API.
        :param UUID cluster_id: An ID that will be included in the names of
            Cinder block devices in order to associate them with a particular
            Flocker cluster.
        """
        self.volume_manager = volume_manager
        self.cluster_id = cluster_id

    def create_volume(self, dataset_id, size):
        """
        Create a block device using the ICinderVolumeManager.
        The cluster_id and dataset_id are stored as metadata on the volume.

        See: http://docs.rackspace.com/cbs/api/v1.0/cbs-devguide/content/POST_createVolume_v1__tenant_id__volumes_volumes.html # noqa

        TODO:
         * Assign a Human readable name and description?
        """
        metadata = {
            CLUSTER_ID_LABEL: unicode(self.cluster_id),
            DATASET_ID_LABEL: unicode(dataset_id),
        }
        # We supply metadata here and it'll be included in the returned cinder
        # volume record, but it'll be lost by Rackspace, so...
        requested_volume = self.volume_manager.create(
            size=Byte(size).to_GB().value,
            metadata=metadata,
        )
        created_volume = wait_for_volume(self.volume_manager, requested_volume)
        # So once the volume has actually been created, we set the metadata
        # again. One day we hope this won't be necessary.
        # See Rackspace support ticket: 150422-ord-0000495'
        self.volume_manager.set_metadata(created_volume, metadata)
        # Use requested volume here, because it has the desired metadata.
        return _blockdevicevolume_from_cinder_volume(requested_volume)

    def list_volumes(self):
        """
        Return ``BlockDeviceVolume`` instances for all the Cinder Volumes that
        have the expected ``cluster_id`` in their metadata.

        See: http://docs.rackspace.com/cbs/api/v1.0/cbs-devguide/content/GET_getVolumesDetail_v1__tenant_id__volumes_detail_volumes.html # noqa
        """
        volumes = []
        for cinder_volume in self.volume_manager.list():
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
    :param UUID cluster_id: The uuid4 of a Flocker cluster.
    :param Volume cinder_volume: The Volume with metadata to examine.
    :return: ``True`` if ``cinder_volume`` metadata has a
    ``CLUSTER_ID_LABEL`` value matching ``cluster_id`` else ``False``.
    """
    actual_cluster_id = cinder_volume.metadata.get(CLUSTER_ID_LABEL)
    if actual_cluster_id == cluster_id:
        return True
    return False


def _blockdevicevolume_from_cinder_volume(cinder_volume):
    """
    :param Volume cinder_volume: The ``cinderclient.v1.volumes.Volume`` to
        convert.
    :returns: A ``BlockDeviceVolume`` based on values found in the supplied
        cinder Volume.
    """
    return BlockDeviceVolume(
        blockdevice_id=unicode(cinder_volume.id),
        size=int(GB(cinder_volume.size).to_Byte().value),
        host=None,
        dataset_id=UUID(cinder_volume.metadata[DATASET_ID_LABEL])
    )


def rackspace_cinder_client(username, api_key, region):
    """
    Create a Cinder API client capable of authenticating with Rackspace and
    communicating with their Cinder API.

    :param unicode username: A RackSpace API username.
    :param unicode api_key: A RackSpace API key.
    :param unicode region: A RackSpace region slug.
    :return: A ``cinderclient.v1.clien.Client`` instance with a ``volumes``
        attribute that conforms to ``ICinderVolumeManager``.
    """
    auth_url = "https://identity.api.rackspacecloud.com/v2.0"
    auth = RackspaceAuth(auth_url=auth_url, username=username, api_key=api_key)
    session = Session(auth=auth)
    return Client(version=1, session=session, region_name=region)


def cinder_api(cinder_client, cluster_id):
    """
    :param cinder_client: The Cinder API client whose ``volumes`` attribute
        will be supplied as the ``volume_manager`` parameter of
        ``CinderBlockDeviceAPI``.
    :param UUID cluster_id: A Flocker cluster ID.
    :returns: A ``CinderBlockDeviceAPI``.
    """
    return CinderBlockDeviceAPI(
        volume_manager=cinder_client.volumes,
        cluster_id=cluster_id,
    )
