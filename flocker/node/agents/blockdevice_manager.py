# -*- test-case-name: flocker.node.agents.test.test_blockdevice_manager -*-
# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
This module implements interactions between the OS pertaining to block devices.
This controls actions such as formatting and mounting a blockdevice.
"""

import psutil
from subprocess import CalledProcessError, check_output, STDOUT

from zope.interface import Interface, implementer

from pyrsistent import PClass, field

from twisted.python.filepath import FilePath


class MountInfo(PClass):
    """
    Information about an existing mount on the system.

    :ivar FilePath blockdevice: The device path to the mounted blockdevice.
    :ivar FilePath mounpoint: The file path to the mount point.
    """
    blockdevice = field(type=FilePath, mandatory=True)
    mountpoint = field(type=FilePath, mandatory=True)


class IBlockDeviceManager(Interface):
    """
    An interface for interactions with the OS pertaining to block devices.
    """

    def make_filesystem(blockdevice, filesystem):
        """
        Format the blockdevice at blockdevice.path with the given filesystem.

        :param FilePath blockdevice: The blockdevice to make the filesystem on.
        :param unicode filesystem: The filesystem type to use.
        """

    def has_filesystem(blockdevice):
        """
        Returns whether the blockdevice at blockdevice.path has a filesystem.

        :param FilePath blockdevice: The bockdevice to query for a filesystem.
        :returns: True if the blockdevice has a filesystem.
        """

    def mount(blockdevice, mountpoint):
        """
        Mounts the blockdevice at blockdevice.path at mountpoint.path.

        :param FilePath blockdevice: The path to the block device to mount.
        :param FilePath mountpoint: The path to mount the block device at.

        :raises: ``UnformattedException`` if the block device is not formatted.
        """

    def unmount(blockdevice):
        """
        Unmounts the blockdevice at blockdevice.path

        :param FilePath blockdevice: The path to the block device to unmount.
        """

    def get_mounts():
        """
        Returns all known mounts on the system.

        :returns: An iterable of ``MountInfo``s of all known mounts.
        """


@implementer(IBlockDeviceManager)
class BlockDeviceManager(PClass):
    """
    Real implementation of IBlockDeviceManager.
    """

    def make_filesystem(self, blockdevice, filesystem):
        check_output([
            b"mkfs", b"-t", filesystem.encode("ascii"),
            # This is ext4 specific, and ensures mke2fs doesn't ask
            # user interactively about whether they really meant to
            # format whole device rather than partition. It will be
            # removed once upstream bug is fixed. See FLOC-2085.
            b"-F",
            blockdevice.path
        ])

    def has_filesystem(self, blockdevice):
        try:
            check_output(
                [b"blkid", b"-p", b"-u", b"filesystem", blockdevice.path],
                stderr=STDOUT,
            )
        except CalledProcessError as e:
            # According to the man page:
            #   the specified token was not found, or no (specified) devices
            #   could be identified
            #
            # Experimentation shows that there is no output in the case of the
            # former, and an error printed to stderr in the case of the
            # latter.
            #
            # FLOC-2388: We're assuming an interface. We should test this
            # assumption.
            if e.returncode == 2 and not e.output:
                # There is no filesystem on this device.
                return False
            raise
        return True

    def mount(self, blockdevice, mountpoint):
        check_output([b"mount", blockdevice.path, mountpoint.path])

    def unmount(self, blockdevice):
        check_output([b"umount", blockdevice.path])

    def get_mounts(self):
        mounts = psutil.disk_partitions()
        return (MountInfo(blockdevice=FilePath(mount.device),
                          mountpoint=FilePath(mount.mountpoint))
                for mount in mounts)
