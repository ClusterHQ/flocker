# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
A Cinder implementation of the ``IBlockDeviceAPI``.

Notes:
* I couldn't get shade working. It's documentation is out of date and when I'd figured out acceptable arguments to supply, I only got authentication failures.
  https://github.com/openstack-infra/shade/
* It uses third party libraries for parsing a "standard" clouds.yaml configuration file and then performing "keystone" authentication.
  But the format of the clouds.yaml file is far from standard and I haven't yet figured out how to debug problems with the keystone authentication step.
* pyrax on the other hand does authenticate, but may not be compatible with non-rackspace OpenStack installations (although it claims to be compatible...I haven't tried)
* I experimented to see if could programatically create Rackspace volumes with metadata. Pyrax allows me to supply the metadata, but it doesn't seem to get saved. (see below)
* I also tried using curl to issue REST API requests directly, but couldn't get the authentication working there either.
* I don't understand OpenStack API authentication mechanism...that's probably the root problem.
* I haven't tried the standard docs.openstack.org/developer/python-cinderclient library, but I guess that *should* be the best option.
  It might be worth experimenting with that a little, especially to see how it handle volume metadata.
"""

from keystoneclient_rackspace.v2_0 import RackspaceAuth
from keystoneclient.session import Session

from cinderclient.client import Client

from zope.interface import implementer

from .blockdevice import IBlockDeviceAPI


@implementer(IBlockDeviceAPI)
class CinderBlockDeviceAPI(object):
    """
    A cinder implementation of ``IBlockDeviceAPI`` which creates block devices
    in an OpenStack cluster.
    """
    def __init__(self, cinder_client, cluster_id, region):
        """
        :param cinderclient.cinder.Client cinder_client: A client for
            interacting with Cinder API.
        :param UUID cluster_id: An ID that will be included in the names of
            Cinder block devices in order to associate them with a particular
            Flocker cluster.
        :param unicode region: A provider specific region identifier string.
        :param pyrax_context: An authenticated pyrax context.
        """

    def create_volume(self, dataset_id, size):
        """
        Create the block device using the volume_driver.
        Store the dataset_id as metadata
        Store the cluster_id as metadata
        Assign a Human readable name and description?
        Eg FLOCKER: Block device for dataset {dataset_id} in cluster {cluster_id}

        ```
        In [10]: volume.create('richardw-test-2', 100, 'SATA', metadata={"flocker_dataset_id": unicode(uuid.uuid4())})
        Out[10]: <CloudBlockStorageVolume attachments=[], availability_zone=nova, bootable=false, created_at=2015-04-17T11:59:48.475838, display_description=, display_name=richardw-test-2, id=c7b08f98-f363-484d-83fb-410927c69159, metadata={u'flocker_dataset_id': u'b816da15-063e-47a4-843d-275ffa37ecec'}, size=100, snapshot_id=None, source_volid=None, status=creating, volume_type=SATA>
        ```

        ONLY TROUBLE IS...that the metadata I supplied doesn't seem to be returned when I then call ``list()`` :-(

        Not sure if that's a problem with pyrax or whether it's simply not possible to store custom metadata for volumes on Rackspace.

        TODO: Tom suggested asking Rackspace directly.

        If it's not possible, we can maybe store the dataset_id etc as JSON in the volume description field...but that sounds awful.

        Return a BlockDeviceVolume via _blockdevicevolume_from_pyrax_volume

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
        # pyrax.volume.create(...)
        # ...then block until the volume status is "available"

    def list_volumes(self):
        """
        Issue a ``detail`` volumes query which will include metadata.
        Return ``BlockDeviceVolume`` instances for all the Cinder devices that have the expected ``cluster_id`` among the metadata.
        Use ``_blockdevicevolume_from_pyrax_volume`` to convert the object returned by the pyrax list method.

        http://docs.rackspace.com/cbs/api/v1.0/cbs-devguide/content/GET_getVolumesDetail_v1__tenant_id__volumes_detail_volumes.html

        See comment above about how pyrax.volume.list doesn't seem to return the metadata that you supply when creating a volume.
        """


def _blockdevicevolume_from_pyrax_volume(blockdevice_id, pyrax_volume):
    """
    ```
    :param CloudBlockStorageVolume pyrax_volume: The pyrax volume object returned by pyrax.volume.list.
    :returns: A ``BlockDeviceVolume`` based on values found in the supplied instance.
    """


def authenticated_cinder_client(username, api_key, region):
    auth_url = "https://identity.api.rackspacecloud.com/v2.0"
    auth = RackspaceAuth(auth_url=auth_url, username=username, api_key=api_key)
    session = Session(auth=auth)
    return Client(version=1, session=session, region_name=region)


def authenticated_cinder_api(cluster_id, username, api_key, region):
    """
    Create a pyrax context for the supplied credentials and return a
    ``CinderBlockDeviceAPI with those.
    """
    cinder_client = authenticated_cinder_client(username, api_key, region)
    return CinderBlockDeviceAPI(cinder_client, cluster_id, region)
