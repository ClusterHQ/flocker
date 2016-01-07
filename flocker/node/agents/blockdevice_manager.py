# -*- test-case-name: flocker.node.agents.test.test_blockdevice_manager -*-
# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Interactions between the OS pertaining to block devices.
This controls actions such as formatting and mounting a blockdevice.
"""

import psutil
from subprocess import CalledProcessError, check_output, STDOUT

from zope.interface import Interface, implementer

from pyrsistent import PClass, field

from twisted.python.filepath import FilePath
from twisted.python.constants import ValueConstant, Values

from characteristic import attributes


class Permissions(Values):
    """
    Constants for permissions for a remount.
    """
    READ_ONLY = ValueConstant("ro")
    READ_WRITE = ValueConstant("rw")


@attributes(["blockdevice", "mountpoint", "source_message"])
class MountError(Exception):
    """
    Raised from errors while mounting a blockdevice.

    :ivar FilePath blockdevice: The path to the blockdevice that was
        being mounted when the error occurred.
    :ivar FilePath mountpoint: The path that the blockdevice was going to be
        mounted at when the error occurred.
    :ivar unicode source_message: The error message describing the error.
    """

    def __str__(self):
        return self.__repr__()


@attributes(["source_path", "mountpoint", "source_message"])
class BindMountError(Exception):
    """
    Raised from errors while bind mounting.

    :ivar FilePath source_path: The source path that was requested to be bind
        mounted.
    :ivar FilePath mountpoint: The path that `source_path` was going to be
        mounted at when the error occurred.
    :ivar unicode source_message: The error message describing the error.
    """

    def __str__(self):
        return self.__repr__()


@attributes(["mountpoint", "permissions", "source_message"])
class RemountError(Exception):
    """
    Raised from errors while remounting a mount point.

    :ivar FilePath mountpoint: The path of the mount to be remounted
    :ivar Permissions permissions: The attempted permissions to remount the
        mountpoint with.
    :ivar unicode source_message: The error message describing the error.
    """

    def __str__(self):
        return self.__repr__()


@attributes(["mountpoint", "source_message"])
class MakeTmpfsMountError(Exception):
    """
    Raised from errors while making a tmpfs mount.

    :ivar FilePath mountpoint: The mountpoint for the new tmpfs mount.
    :ivar unicode source_message: The error message describing the error.
    """

    def __str__(self):
        return self.__repr__()


@attributes(["blockdevice", "source_message"])
class MakeFilesystemError(Exception):
    """Raised from errors while making a filesystem on a blockdevice.

    :ivar FilePath blockdevice: The path to the blockdevice that was
        being formatted when the error occurred.
    :ivar unicode source_message: The error message describing the error.
    """

    def __str__(self):
        return self.__repr__()


@attributes(["blockdevice", "source_message"])
class UnmountError(Exception):
    """Raised from errors while unmounting a blockdevice.

    :ivar FilePath blockdevice: The path to the blockdevice that was
        being unmounted when the error occurred.
    :ivar unicode source_message: The error message describing the error.
    """

    def __str__(self):
        return self.__repr__()


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

        :raises: ``MakeFilesystemError`` on any failure from the system. This
            includes user kill signals, so this may even be raised on
            successful runs of mkfs.
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

        :raises: ``MountError`` on any failure from the system. This includes
            user kill signals, so this may even be raised on successful mounts.
        """

    def unmount(blockdevice):
        """
        Unmounts the blockdevice at blockdevice.path

        :param FilePath blockdevice: The path to the block device to unmount.

        :raises: ``UnmountError`` on any failure from the system. This includes
            user kill signals, so this may even be raised on successful runs of
            umount.
        """

    def get_mounts():
        """
        Returns all known disk device mounts on the system.

        This only includes mounted block devices and not tmpfs mounts or bind
        mounts.

        :returns: An iterable of ``MountInfo``s of all known mounts.
        """

    def bind_mount(source_path, mountpoint):
        """
        Bind mounts ``source_path`` at ``mountpoint``.

        :param FilePath source_path: The path to be bind mounted.
        :param FilePath mountpoint: The target path for the mount.

        :raises: ``BindMountError`` on any failure from the system. This
            includes user kill signals, so this may even be raised on
            successful bind mounts.
        """

    def remount(mountpoint, permissions):
        """
        Remounts ``mountpoint`` with the given permissions.

        :param FilePath mountpoint: The target path for the mount.
        :param Permissions permissions: The permissions to remount the
            mountpoint with.

        :raises: ``RemountError`` on any failure from the system. This includes
            user kill signals, so this may even be raised on successful
            remounts.
        """

    def make_tmpfs_mount(mountpoint):
        """
        Creates a tmpfs mount at the given mountpoint.

        :param FilePath mountpoint: The target path for the mount.

        :raises: ``MakeTmpfsMountError`` on any failure from the system. This
            includes user kill signals, so this may even be raised on
            successful mounts.
        """


class _CommandResult(PClass):
    """
    Helper object to represent the result of a command.

    :ivar bool succeeded: True if the command was successful otherwise false.
    :ivar unicode error_message: Message that would be useful to output on
        failure. Only set if the command did not succeed.
    """
    succeeded = field(type=bool)
    error_message = field(type=unicode, mandatory=False)


def _run_command(command_arg_list):
    """
    Helper wrapper to run a command and capture STDOUT and STDERR if the
    command fails. Used for common code in the implementation of many methods
    of the interface.

    :param command_arg_list: Command arguments that will be passed directly as
        the first argument of check_output.

    :returns _CommandResult: The representation of the result of the command.
    """
    try:
        check_output(command_arg_list, stderr=STDOUT)
    except CalledProcessError as e:
        return _CommandResult(
            succeeded=False,
            error_message=u"\n".join([str(e), e.output]))
    return _CommandResult(succeeded=True)


@implementer(IBlockDeviceManager)
class BlockDeviceManager(PClass):
    """
    Real implementation of IBlockDeviceManager.
    """

    def make_filesystem(self, blockdevice, filesystem):
        result = _run_command([
            b"mkfs", b"-t", filesystem.encode("ascii"),
            # This is ext4 specific, and ensures mke2fs doesn't ask
            # user interactively about whether they really meant to
            # format whole device rather than partition. It will be
            # removed once upstream bug is fixed. See FLOC-2085.
            b"-F",
            blockdevice.path
        ])
        if not result.succeeded:
            raise MakeFilesystemError(blockdevice=blockdevice,
                                      source_message=result.error_message)

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
        result = _run_command([b"mount", blockdevice.path, mountpoint.path])
        if not result.succeeded:
            raise MountError(blockdevice=blockdevice, mountpoint=mountpoint,
                             source_message=result.error_message)

    def unmount(self, blockdevice):
        result = _run_command([b"umount", blockdevice.path])
        if not result.succeeded:
            raise UnmountError(blockdevice=blockdevice,
                               source_message=result.error_message)

    def get_mounts(self):
        mounts = psutil.disk_partitions()
        return (MountInfo(blockdevice=FilePath(mount.device),
                          mountpoint=FilePath(mount.mountpoint))
                for mount in mounts)

    def bind_mount(self, source_path, mountpoint):
        result = _run_command(
            [b"mount", "--bind", source_path.path, mountpoint.path])
        if not result.succeeded:
            raise BindMountError(source_path=source_path,
                                 mountpoint=mountpoint,
                                 source_message=result.error_message)

    def remount(self, mountpoint, permissions):
        result = _run_command([
            b"mount", "-o", "remount,%s" % permissions.value, mountpoint.path])
        if not result.succeeded:
            raise RemountError(mountpoint=mountpoint,
                               permissions=permissions,
                               source_message=result.error_message)

    def make_tmpfs_mount(self, mountpoint):
        result = _run_command(
            [b"mount", "-t", "tmpfs", "tmpfs", mountpoint.path])
        if not result.succeeded:
            raise MakeTmpfsMountError(mountpoint=mountpoint,
                                      source_message=result.error_message)
