# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
A Cinder implementation of the ``IBlockDeviceAPI``.
"""
import string
from subprocess import check_output
import time
from uuid import UUID
from subprocess import check_output

from bitmath import Byte, GB

from keystoneclient_rackspace.v2_0 import RackspaceAuth
from keystoneclient.session import Session

from twisted.python.filepath import FilePath
from zope.interface import implementer, Interface

from .blockdevice import (
    IBlockDeviceAPI, BlockDeviceVolume, UnknownVolume, AlreadyAttachedVolume
)

# The key name used for identifying the Flocker cluster_id in the metadata for
# a volume.
CLUSTER_ID_LABEL = u'flocker-cluster-id'

# The key name used for identifying the Flocker dataset_id in the metadata for
# a volume.
DATASET_ID_LABEL = u'flocker-dataset-id'

# The Rackspace authentication endpoint
# See http://docs.rackspace.com/cbs/api/v1.0/cbs-devguide/content/Authentication-d1e647.html # noqa
RACKSPACE_AUTH_URL = "https://identity.api.rackspacecloud.com/v2.0"


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

class INovaVolumeManager(Interface):
    """
    The parts of ``novaclient.v2.volumes.VolumeManager`` that we use.
    See: https://github.com/openstack/python-novaclient/blob/master/novaclient/v2/volumes.py # noqa
    """
    def create_server_volume(server_id, volume_id, device):
        """
        Attach a volume identified by the volume ID to the given server ID

        :param server_id: The ID of the server
        :param volume_id: The ID of the volume to attach.
        :param device: The device name
        :rtype: :class:`Volume`        
        """


def wait_for_volume(volume_manager, expected_volume,
                    expected_status=u'available',
                    time_limit=60):
    """
    Wait for a ``Volume`` with the same ``id`` as ``expected_volume`` to be
    listed and to have a ``status`` value of ``expected_status``.

    :param ICinderVolumeManager volume_manager: An API for listing volumes.
    :param Volume expected_volume: The ``Volume`` to wait for.
    :param unicode expected_status: The ``Volume.status`` to wait for.
    :param int time_limit: The maximum time, in seconds, to wait for the
        ``expected_volume`` to have ``expected_status``.
    :raises Exception: If ``expected_volume`` with ``expected_status`` is not
        listed within ``time_limit``.
    :returns: The listed ``Volume`` that matches ``expected_volume``.
    """
    start_time = time.time()
    while True:
        # Simplify this: use expected_volume.get() to update in place instead
        # (MUTATION IS THE BEST).
        for listed_volume in volume_manager.list():
            if listed_volume.id == expected_volume.id:
                if listed_volume.status == expected_status:
                    return listed_volume

        elapsed_time = time.time() - start_time
        if elapsed_time < time_limit:
            time.sleep(0.1)
        else:
            raise Exception(
                'Timed out while waiting for volume. '
                'Expected Volume: {!r}, '
                'Expected Status: {!r}, '
                'Elapsed Time: {!r}, '
                'Time Limit: {!r}.'.format(
                    expected_volume, expected_status, elapsed_time, time_limit
                )
            )


2@implementer(IBlockDeviceAPI)
class CinderBlockDeviceAPI(object):
    """
    A cinder implementation of ``IBlockDeviceAPI`` which creates block devices
    in an OpenStack cluster using Cinder APIs.
    """
    def __init__(self, cinder_volume_manager, nova_volume_manager, cluster_id, host_map):
        """
        :param ICinderVolumeManager cinder_volume_manager: A client for interacting
            with Cinder API.
        :param INovaServerManager nova_volume_manager: A client for interacting
            with Nova volume API.
        :param UUID cluster_id: An ID that will be included in the names of
            Cinder block devices in order to associate them with a particular
            Flocker cluster.
        """
        self.cinder_volume_manager = cinder_volume_manager
        self.nova_volume_manager = nova_volume_manager
        self.cluster_id = cluster_id
        self.host_map = host_map
        self.reverse_host_map = dict((v, k) for k, v in host_map.items())

    def compute_instance_id(self):
        """
        Look up the Xen instance ID for this node.
        """
        # See http://wiki.christophchamp.com/index.php/Xenstore
        # $ sudo xenstore-read name
        # instance-6ddfb6c0-d264-4e77-846a-aa67e4fe89df
        command = [b"xenstore-read", b"name"]
        return check_output(command).strip().decode("ascii")

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
        requested_volume = self.cinder_volume_manager.create(
            size=Byte(size).to_GB().value,
            metadata=metadata,
        )
        created_volume = wait_for_volume(self.cinder_volume_manager, requested_volume)
        # So once the volume has actually been created, we set the metadata
        # again. One day we hope this won't be necessary.
        # See Rackspace support ticket: 150422-ord-0000495'
        self.cinder_volume_manager.set_metadata(created_volume, metadata)
        # Use requested volume here, because it has the desired metadata.
        return _blockdevicevolume_from_cinder_volume(
            cinder_volume=requested_volume, 
            host_map=self.reverse_host_map,
        )

    def list_volumes(self):
        """
        Return ``BlockDeviceVolume`` instances for all the Cinder Volumes that
        have the expected ``cluster_id`` in their metadata.

        See: http://docs.rackspace.com/cbs/api/v1.0/cbs-devguide/content/GET_getVolumesDetail_v1__tenant_id__volumes_detail_volumes.html # noqa
        """
        flocker_volumes = []
        for cinder_volume in self.cinder_volume_manager.list():
            if _is_cluster_volume(self.cluster_id, cinder_volume):
                flocker_volume = _blockdevicevolume_from_cinder_volume(cinder_volume, self.reverse_host_map)
                flocker_volumes.append(flocker_volume)
        return flocker_volumes

    def _get(self, blockdevice_id):
        for volume in self.list_volumes():
            if volume.blockdevice_id == blockdevice_id:
                return volume
        raise UnknownVolume(blockdevice_id)

    def resize_volume(self, blockdevice_id, size):
        pass

    def attach_volume(self, blockdevice_id, attach_to):
        """
        The attaching may have to be done via the nova client :-(
        See http://www.florentflament.com/blog/openstack-volume-in-use-although-vm-doesnt-exist.html # noqa

        When I attach using the cinder client the volumes become undetachable.
        """
        unattached_volume = self._get(blockdevice_id)
        if unattached_volume.attached_to is not None:
            raise AlreadyAttachedVolume(blockdevice_id)

        nova_volume = self.nova_volume_manager.create_server_volume(
            # Nova API expects an ID string not UUID.
            server_id=attach_to,
            volume_id=unattached_volume.blockdevice_id,
            # Have Nova assign a device file for us.
            device=None,
        )
        attached_volume = wait_for_volume(
            volume_manager=self.cinder_volume_manager,
            expected_volume=nova_volume,
            expected_status=u'in-use',
        )

        attached_volume = unattached_volume.set('attached_to', attach_to)

        return attached_volume

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
    if actual_cluster_id is not None:
        actual_cluster_id = UUID(actual_cluster_id)
        if actual_cluster_id == cluster_id:
            return True
    return False


def _blockdevicevolume_from_cinder_volume(cinder_volume, host_map):
    """
    :param Volume cinder_volume: The ``cinderclient.v1.volumes.Volume`` to
        convert.
    :returns: A ``BlockDeviceVolume`` based on values found in the supplied
        cinder Volume.
    """
    if cinder_volume.attachments:
        # There should only be one.
        [attachment_info] = cinder_volume.attachments
        # Nova and Cinder APIs return ID strings. Convert to UUID
        # before looking up.
        server_id = UUID(attachment_info['server_id'])
        flocker_host = host_map[server_id]
    else:
        flocker_host = None
    
    return BlockDeviceVolume(
        blockdevice_id=unicode(cinder_volume.id),
        size=int(GB(cinder_volume.size).to_Byte().value),
        attached_to=flocker_host,
        dataset_id=UUID(cinder_volume.metadata[DATASET_ID_LABEL])
    )


def rackspace_session(**kwargs):
    """
    Create a Keystone session capable of authenticating with Rackspace.

    :param unicode username: A RackSpace API username.
    :param unicode api_key: A RackSpace API key.
    :param unicode region: A RackSpace region slug.
    :return: A ``keystoneclient.session.Session``.
    """
    username = kwargs.pop('username')
    api_key = kwargs.pop('key')

    auth = RackspaceAuth(
        auth_url=RACKSPACE_AUTH_URL,
        username=username,
        api_key=api_key
    )
    return Session(auth=auth)


SESSION_FACTORIES = {
    'rackspace': rackspace_session,
}


def cinder_api(cinder_client, nova_client, cluster_id, host_map):
    """
    :param cinderclient.v1.client.Client cinder_client: The Cinder API client
        whose ``volumes`` attribute will be supplied as the ``cinder_volume_manager``
        parameter of ``CinderBlockDeviceAPI``.
    :param novaclient.v2.client.Client nova_client: The Nova API client
        whose ``volumes`` attribute will be supplied as the ``nova_volume_manager``
        parameter of ``CinderBlockDeviceAPI``.
    :param UUID cluster_id: A Flocker cluster ID.
    :returns: A ``CinderBlockDeviceAPI``.
    """
    return CinderBlockDeviceAPI(
        cinder_volume_manager=cinder_client.volumes,
        nova_volume_manager=nova_client.volumes,
        cluster_id=cluster_id,
        host_map=host_map,
    )
