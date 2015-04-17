# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
A Cinder implementation of the ``IBlockDeviceAPI``.
"""
import pyrax

from .blockdevice import IBlockDeviceAPI


class CinderBlockDeviceAPI(object):
    """
    A cinder implementation of ``IBlockDeviceAPI`` which creates block devices
    in an OpenStack cluster.
    """
    def __init__(self, cluster_id, volume_driver, compute_driver):
        """
        :param UUID cluster_id: An ID that will be included in the names of
            Cinder block devices in order to associate them with a particular
            Flocker cluster.
        :param volume_driver: A pyrax volume driver (locked to a specific region)
        :param compute_driver: A pyrax compute driver (locked to a specific region)
        """
        # Assign the volume and compute drivers to instance variables.
        # Maybe we'll need the pyrax context too? So perhaps we should just
        # store that instead.

    def create_volume(self, dataset_id, size):
        """
        Create the block device using the volume_driver.
        Store the dataset_id as metadata
        Store the cluster_id as metadata
        Assign a Human readable name and description?
        Eg FLOCKER: Block device for dataset {dataset_id} in cluster {cluster_id}

        Return a BlockDeviceVolume.

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

    def list_volumes(self):
        """
        Issue a ``detail`` volumes query which will include metadata
        Return ``BlockDeviceVolume`` instances for all the Cinder devices that have the expected ``cluster_id`` in their name.
        Extract the dataset_id from the metadata.

        http://docs.rackspace.com/cbs/api/v1.0/cbs-devguide/content/GET_getVolumesDetail_v1__tenant_id__volumes_detail_volumes.html
        """


def authenticated_cinder_api(cluster_id, username, api_key, region, id_type="rackspace"):
    """
    Create a pyrax context for the supplied credentials and return a
    ``CinderBlockDeviceAPI with those.
    """
    # See https://github.com/ClusterHQ/flocker/compare/openstack-spike-FLOC-1147#diff-f958e4076e410717193f3dd33c9a9919R47
    pyrax_context = pyrax.create_context(
        id_type=id_type, username=username, api_key=api_key
    )
    pyrax_context.authenticate()
    volume_driver = pyrax_context.get_client('volume', region)
    compute_driver = pyrax_context.get_client('compute', region)
    return CinderBlockDeviceAPI(cluster_id, volume_driver, compute_driver)
