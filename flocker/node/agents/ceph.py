"""
Experimental Ceph RADOS Block Device Driver.

XXX Implementation notes:

Ceph RBD creates "images". These have are units of storage within Ceph, like an
EBS volume. The image is given a name. The image is then "map"ped, referenced
by name, onto an OS block device. This OS block device can then be used in the
normal fashion. The images can be mapped to multiple nodes simultaneously, so
they must be handled carefully. The output of the `rbd map` command is the OS
block device name, but it is also located at /dev/rbd/rbd/<image-name>.

Ceph images can also be stored in named pools (optional). This should be
presented to the user at some point.
"""
@implementer(IBlockDeviceAPI)
class CephBlockDeviceAPI(object):
    """
    An implementation of ``IBlockDeviceAPI`` for the Ceph RADOS Block Device
    (RBD).
    """
    def __init__(self, ceph_runner, cluster_id):
        """
        Initialize Ceph RBD API instance.

        :param CommandRunner ceph_runner: A command runner for ceph commands.
        :param UUID cluster_id: UUID of cluster for this
            API instance.
        """
        self.runner = ceph_runner
        self.cluster_id = cluster_id
        self.lock = threading.Lock()

    def allocation_unit(self):
        """
        Block device images are specified in units of 1 MiB.

        http://docs.ceph.com/docs/giant/man/8/rbd/
        """
        return int(MiB(1).to_Byte().value)


    def create_volume(self, dataset_id, size):
        """
        Create a Ceph image.

        XXX can't store metadata
        """

        # Return created volume in BlockDeviceVolume format.
        return _blockdevicevolume_from_ceph_image()

    def list_volumes(self):
        """
        Return all volumes that belong to this Flocker cluster.

        return list of BlockDeviceVolume objects.
        """

    def attach_volume(self, blockdevice_id, attach_to):
        """
        Map a Ceph image to this node.

        :param unicode blockdevice_id: Ceph UUID for volume to be attached.
        :param unicode attach_to: Instance id of Ceph node to attached the
        blockdevice to.

        :raises UnknownVolume: If there does not exist a BlockDeviceVolume
            corresponding to the input blockdevice_id.
        :raises AlreadyAttachedVolume: If the input image is already attached
            to a device.
        :raises AttachedUnexpectedDevice: If the attach operation fails to
            associate the image with the expected OS device file.
        """

    def detach_volume(self, blockdevice_id):
        """
        Unmap a Ceph image from its mapped node.

        :param unicode blockdevice_id: EBS UUID for volume to be detached.

        :raises UnknownVolume: If there does not exist a BlockDeviceVolume
            corresponding to the input blockdevice_id.
        :raises UnattachedVolume: If the BlockDeviceVolume for the
            blockdevice_id is not currently 'in-use'.
        """

    def destroy_volume(self, blockdevice_id):
        """
        Destroy a Ceph image. If the image has snapshots, remove all the
        snapshots first.

        :raises UnknownVolume: If there does not exist a Flocker cluster
            volume identified by input blockdevice_id.
        :raises Exception: If we failed to destroy Flocker cluster volume
            corresponding to input blockdevice_id.
        """

    def get_device_path(self, blockdevice_id):
        """
        Get device path for the Ceph image corresponding to the given
        block device.

        :param unicode blockdevice_id: Ceph image name for the volume to look
            up.

        :returns: A ``FilePath`` for the device.
        :raises UnknownVolume: If the supplied ``blockdevice_id`` does not
            exist.
        :raises UnattachedVolume: If the supplied ``blockdevice_id`` is
            not attached to a host.
        """
