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
        Create a volume on EBS. Store Flocker-specific
        {metadata version, cluster id, dataset id} for the volume
        as volume tag data.
        Open issues: https://clusterhq.atlassian.net/browse/FLOC-1792
        """
        requested_volume = self.connection.create_volume(
            size=int(Byte(size).to_GiB().value), zone=self.zone)

        # Stamp created volume with Flocker-specific tags.
        metadata = {
            METADATA_VERSION_LABEL: '1',
            CLUSTER_ID_LABEL: unicode(self.cluster_id),
            DATASET_ID_LABEL: unicode(dataset_id),
            # EC2 convention for naming objects, e.g. as used in EC2 web
            # console (http://stackoverflow.com/a/12798180).
            "Name": u"flocker-{}".format(dataset_id),
        }
        self.connection.create_tags([requested_volume.id],
                                    metadata)

        # Wait for created volume to reach 'available' state.
        _wait_for_volume_state_change(VolumeOperations.CREATE,
                                      requested_volume)

        # Return created volume in BlockDeviceVolume format.
        return _blockdevicevolume_from_ebs_volume(requested_volume)

    def list_volumes(self):
        """
        Return all volumes that belong to this Flocker cluster.
        """
        try:
            ebs_volumes = self.connection.get_all_volumes()
        except EC2ResponseError as e:
            # Work around some internal race-condition in EBS by retrying,
            # since this error makes no sense:
            if e.code == NOT_FOUND:
                return self.list_volumes()
            else:
                raise

        volumes = []
        for ebs_volume in ebs_volumes:
            if _is_cluster_volume(self.cluster_id, ebs_volume):
                volumes.append(
                    _blockdevicevolume_from_ebs_volume(ebs_volume)
                )
        return volumes

    def attach_volume(self, blockdevice_id, attach_to):
        """
        Attach an EBS volume to given compute instance.

        :param unicode blockdevice_id: EBS UUID for volume to be attached.
        :param unicode attach_to: Instance id of AWS Compute instance to
            attached the blockdevice to.

        :raises UnknownVolume: If there does not exist a BlockDeviceVolume
            corresponding to the input blockdevice_id.
        :raises AlreadyAttachedVolume: If the input volume is already attached
            to a device.
        :raises AttachedUnexpectedDevice: If the attach operation fails to
            associate the volume with the expected OS device file.  This
            indicates use on an unsupported OS, a misunderstanding of the EBS
            device assignment rules, or some other bug in this implementation.
        """
        ebs_volume = self._get_ebs_volume(blockdevice_id)
        volume = _blockdevicevolume_from_ebs_volume(ebs_volume)
        if (volume.attached_to is not None or
                ebs_volume.status != VolumeStates.AVAILABLE.value):
            raise AlreadyAttachedVolume(blockdevice_id)

        ignore_devices = pset([])
        attach_attempts = 0
        while True:
            with self.lock:
                # begin lock scope

                blockdevices = FilePath(b"/sys/block").children()
                volumes = self.connection.get_all_volumes()
                device = self._next_device(attach_to, volumes, ignore_devices)

                if device is None:
                    # XXX: Handle lack of free devices in ``/dev/sd[f-p]``.
                    # (https://clusterhq.atlassian.net/browse/FLOC-1887).
                    # No point in attempting an ``attach_volume``, return.
                    return

                try:
                    self.connection.attach_volume(blockdevice_id,
                                                  attach_to,
                                                  device)
                except EC2ResponseError as e:
                    # If attach failed that is often because of eventual
                    # consistency in AWS, so let's ignore this one if it
                    # fails:
                    if e.code == u'InvalidParameterValue':
                        attach_attempts += 1
                        if attach_attempts == MAX_ATTACH_RETRIES:
                            raise
                        ignore_devices = ignore_devices.add(device)
                    else:
                        raise
                else:
                    # Wait for new device to manifest in the OS. Since there
                    # is currently no standardized protocol across Linux guests
                    # in EC2 for mapping `device` to the name device driver
                    # picked (http://docs.aws.amazon.com/AWSEC2/latest/
                    # UserGuide/device_naming.html), wait for new block device
                    # to be available to the OS, and interpret it as ours.
                    # Wait under lock scope to reduce false positives.
                    device_path = _wait_for_new_device(
                        blockdevices, volume.size
                    )
                    # We do, however, expect the attached device name to follow
                    # a certain simple pattern.  Verify that now and signal an
                    # error immediately if the assumption is violated.  If we
                    # let it go by, a later call to ``get_device_path`` will
                    # quietly produce the wrong results.
                    #
                    # To make this explicit, we *expect* that the device will
                    # *always* be what we *expect* the device to be (sorry).
                    # This check is only here in case we're wrong to make the
                    # system fail in a less damaging way.
                    if _expected_device(device) != device_path:
                        # We also don't want anything to re-discover the volume
                        # in an attached state since that might also result in
                        # use of ``get_device_path`` (producing an incorrect
                        # result).  This is a best-effort.  It's possible the
                        # agent will crash after attaching the volume and
                        # before detaching it here, leaving the system in a bad
                        # state.  This is one reason we need a better solution
                        # in the long term.
                        self.detach_volume(blockdevice_id)
                        raise AttachedUnexpectedDevice(device, device_path)
                    break
                # end lock scope

        _wait_for_volume_state_change(VolumeOperations.ATTACH, ebs_volume)

        attached_volume = volume.set('attached_to', attach_to)
        return attached_volume

    def detach_volume(self, blockdevice_id):
        """
        Detach EBS volume identified by blockdevice_id.

        :param unicode blockdevice_id: EBS UUID for volume to be detached.

        :raises UnknownVolume: If there does not exist a BlockDeviceVolume
            corresponding to the input blockdevice_id.
        :raises UnattachedVolume: If the BlockDeviceVolume for the
            blockdevice_id is not currently 'in-use'.
        """
        ebs_volume = self._get_ebs_volume(blockdevice_id)
        if ebs_volume.status != VolumeStates.IN_USE.value:
            raise UnattachedVolume(blockdevice_id)

        self.connection.detach_volume(blockdevice_id)

        _wait_for_volume_state_change(VolumeOperations.DETACH, ebs_volume)

    def destroy_volume(self, blockdevice_id):
        """
        Destroy EBS volume identified by blockdevice_id.

        :param String blockdevice_id: EBS UUID for volume to be destroyed.

        :raises UnknownVolume: If there does not exist a Flocker cluster
            volume identified by input blockdevice_id.
        :raises Exception: If we failed to destroy Flocker cluster volume
            corresponding to input blockdevice_id.
        """
        ebs_volume = self._get_ebs_volume(blockdevice_id)
        destroy_result = self.connection.delete_volume(blockdevice_id)
        if destroy_result:
            try:
                _wait_for_volume_state_change(VolumeOperations.DESTROY,
                                              ebs_volume)
            except UnknownVolume:
                return
        else:
            raise Exception(
                'Failed to delete volume: {!r}'.format(blockdevice_id)
            )

    def get_device_path(self, blockdevice_id):
        """
        Get device path for the EBS volume corresponding to the given
        block device.

        :param unicode blockdevice_id: EBS UUID for the volume to look up.

        :returns: A ``FilePath`` for the device.
        :raises UnknownVolume: If the supplied ``blockdevice_id`` does not
            exist.
        :raises UnattachedVolume: If the supplied ``blockdevice_id`` is
            not attached to a host.
        """
        ebs_volume = self._get_ebs_volume(blockdevice_id)
        volume = _blockdevicevolume_from_ebs_volume(ebs_volume)
        if volume.attached_to is None:
            raise UnattachedVolume(blockdevice_id)

        compute_instance_id = self.compute_instance_id()
        if volume.attached_to != compute_instance_id:
            # This is untested.  See FLOC-2453.
            raise Exception(
                "Volume is attached to {}, not to {}".format(
                    volume.attached_to, compute_instance_id
                )
            )

        return _expected_device(ebs_volume.attach_data.device)

