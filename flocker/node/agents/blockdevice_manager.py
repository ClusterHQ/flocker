# -*- test-case-name: flocker.node.agents.test.test_blockdevice_manager -*-
# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Interactions between the OS pertaining to block devices.
This controls actions such as formatting and mounting a blockdevice.
"""

import psutil
from subprocess import CalledProcessError

from zope.interface import Attribute, Interface, implementer
from zope.interface.interface import (
    adapter_hooks as zope_interface_adapter_hooks
)

from pyrsistent import PClass, field

from twisted.python.filepath import FilePath
from twisted.python.constants import ValueConstant, Values

from characteristic import attributes

from ...common.process import run_process
from ...common import temporary_directory
from ...common._filepath import IFilePathExtended


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


@implementer(IBlockDeviceManager)
class BlockDeviceManager(PClass):
    """
    Real implementation of IBlockDeviceManager.
    """
    def make_filesystem(self, blockdevice, filesystem):
        try:
            run_process([
                b"mkfs", b"-t", filesystem.encode("ascii"),
                # This is ext4 specific, and ensures mke2fs doesn't ask
                # user interactively about whether they really meant to
                # format whole device rather than partition. It will be
                # removed once upstream bug is fixed. See FLOC-2085.
                b"-F",
                blockdevice.path
            ])
        except CalledProcessError as e:
            raise MakeFilesystemError(blockdevice=blockdevice,
                                      source_message=e.output)

    def has_filesystem(self, blockdevice):
        try:
            run_process(
                [b"blkid", b"-p", b"-u", b"filesystem", blockdevice.path]
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
        try:
            run_process([b"mount", blockdevice.path, mountpoint.path])
        except CalledProcessError as e:
            raise MountError(blockdevice=blockdevice, mountpoint=mountpoint,
                             source_message=e.output)

    def unmount(self, blockdevice):
        try:
            run_process([b"umount", blockdevice.path])
        except CalledProcessError as e:
            raise UnmountError(blockdevice=blockdevice,
                               source_message=e.output)

    def get_mounts(self):
        mounts = psutil.disk_partitions()
        return (MountInfo(blockdevice=FilePath(mount.device),
                          mountpoint=FilePath(mount.mountpoint))
                for mount in mounts)

    def bind_mount(self, source_path, mountpoint):
        try:
            run_process(
                [b"mount", "--bind", source_path.path, mountpoint.path])
        except CalledProcessError as e:
            raise BindMountError(source_path=source_path,
                                 mountpoint=mountpoint,
                                 source_message=e.output)

    def remount(self, mountpoint, permissions):
        try:
            run_process([
                b"mount", "-o", "remount,%s" % permissions.value,
                mountpoint.path])
        except CalledProcessError as e:
            raise RemountError(mountpoint=mountpoint,
                               permissions=permissions,
                               source_message=e.output)

    def make_tmpfs_mount(self, mountpoint):
        try:
            run_process(
                [b"mount", "-t", "tmpfs", "tmpfs", mountpoint.path])
        except CalledProcessError as e:
            raise MakeTmpfsMountError(mountpoint=mountpoint,
                                      source_message=e.output)


def _unmount(path, idempotent=False):
    """
    Unmount the path (directory or device path).
    """
    try:
        # Do lazy umount.
        run_process(['umount', '-l', path.path])
    except CalledProcessError as e:
        # If idempotent, swallow the case where the mountpoint is no longer
        # mounted.
        # umount on Ubuntu 14.04 returns 1 in this case. On newer OS the return
        # code is 32.
        if idempotent and e.returncode in (1, 32):
            pass
        else:
            raise UnmountError(
                blockdevice=path.path,
                source_message=e.output,
            )


class IMountableFilesystem(Interface):
    """
    An filesystem identifier that can be supplied to ``mount``.
    """
    def identifier():
        """
        :returns: ``unicode`` An identifier which can be understood by the
        ``mount`` command.
        """

    def device_path():
        """
        :returns: ``FilePath`` A device on the filesystem.
        """


class IMountedFilesystem(Interface):
    """
    Represents a mounted filesystem which can be unmounted.  If used as a
    context manager, the mountpoint path will be made available on __enter__
    and the filesystem will be unmounted on __exit__.
    """
    mountpoint = Attribute("An ``IMountpoint`` object.")

    def unmount():
        """
        """

    def __enter__():
        """
        Enter the context of a context manager.
        """

    def __exit__(exc_type, exc_value, traceback):
        """
        Exit the context of a context manager and unmount.
        """


def interface_field(interfaces, **field_kwargs):
    """
    A ``PClass`` field which checks that the assigned value provides all the
    ``interfaces``.

    :param tuple interfaces: The ``Interface`` that a value must provide.
    """
    if not isinstance(interfaces, tuple):
        raise TypeError(
            "The ``interfaces`` argument must be a tuple. "
            "Got: {!r}".format(interfaces)
        )

    original_invariant = field_kwargs.pop("invariant", None)

    def invariant(value):
        error_messages = []
        if original_invariant is not None:
            (original_invariant_result,
             _original_invariant_message) = original_invariant(value)
            if original_invariant_result:
                error_messages.append(original_invariant_result)

        missing_interfaces = []
        for interface in interfaces:
            if not interface.providedBy(value):
                missing_interfaces.append(interface.getName())
        if missing_interfaces:
            error_messages.append(
                "The value {!r} "
                "did not provide these required interfaces: {}".format(
                    value,
                    ", ".join(missing_interfaces)
                )
            )
        if error_messages:
            return (False, "\n".join(error_messages))
        else:
            return (True, "")
    field_kwargs["invariant"] = invariant
    return field(**field_kwargs)


@implementer(IMountableFilesystem)
class DevicePathFilesystem(PClass):
    """
    A filesystem to be mounted by device path.
    """
    path = field(type=FilePath)

    def identifier(self):
        return self.path.path

    def device_path(self):
        return self.path


@implementer(IMountableFilesystem)
class LabelledFilesystem(PClass):
    """
    A filesystem to be mounted by LABEL.
    """
    label = field(type=unicode)

    def identifier(self):
        return 'LABEL=%s' % (self.label.encode('ascii'),)

    def device_path(self):
        return FilePath("/dev/disk/by-label").child(self.label)


IMOUNTABLE_FILESYSTEM_ADAPTERS = {
    # Detect FilePath like objects
    IFilePathExtended.providedBy: lambda obj: DevicePathFilesystem(path=obj),
}


def _adapt(iface, obj):
    """
    Adapt the ``filesystem`` argument of ``mount`` to ``IMountableFilesystem``.
    """
    for wrapper_test, wrapper in IMOUNTABLE_FILESYSTEM_ADAPTERS.items():
        if wrapper_test(obj):
            return wrapper(obj)

zope_interface_adapter_hooks.append(_adapt)


@implementer(IMountedFilesystem)
class MountedFileSystem(PClass):
    """
    A directory where a filesystem is mounted.
    """
    mountpoint = interface_field((IFilePathExtended,), mandatory=True)

    def unmount(self):
        _unmount(self.mountpoint)

    def __enter__(self):
        return self.mountpoint

    def __exit__(self, exc_type, exc_value, traceback):
        self.unmount()


def mount(filesystem, mountpoint, options=None):
    """
    Mount ``filesystem`` at ``mountpoint`` with ``options``.

    :param IMountableFilesystem filesystem: An object by which to identify the
        filesystem.
    :param IFilePathExtended mountpoint: A directory at which to mount.
    :param list options: A list of --option parameters for the mount command.
    :returns: ``IMountedFilesystem``.
    """
    # Adapt the supplied type. Allows a FilePath to be supplied instead.
    filesystem = IMountableFilesystem(filesystem)
    command = ["mount"]
    if options:
        command.extend(["--options", ",".join(options)])
    command.extend([filesystem.identifier(), mountpoint.path])
    try:
        run_process(command)
    except CalledProcessError as e:
        raise MountError(
            blockdevice=filesystem.device_path(),
            mountpoint=mountpoint,
            source_message=e.output,
        )
    return MountedFileSystem(
        mountpoint=mountpoint
    )


@implementer(IMountedFilesystem)
class TemporaryMountedFilesystem(PClass):
    """
    A wrapper which will remove the mountpoint directory when it has been
    unmounted.
    """
    fs = interface_field((IMountedFilesystem,), mandatory=True)

    @property
    def mountpoint(self):
        return self.fs.mountpoint

    def unmount(self):
        self.fs.unmount()
        self.fs.mountpoint.remove()

    def __enter__(self):
        return self.fs.__enter__()

    def __exit__(self, exc_type, exc_value, traceback):
        self.unmount()


def temporary_mount(filesystem, options=None):
    """
    Mount ``filesystem`` at a temporary mountpoint with ``options``.
    A temporary mountpoint directory will be created.
    It will be removed if the mount fails and when the mounted filesystem is
    unmounted.

    :param IMountableFilesystem filesystem: An object by which to identify the
        filesystem.
    :param list options: A list of --option parameters for the mount command.
    :returns: ``IMountedFilesystem``.
    """
    mountpoint = temporary_directory()
    try:
        mounted_fs = mount(filesystem, mountpoint, options=options)
    except:
        mountpoint.remove()
        raise

    return TemporaryMountedFilesystem(
        fs=mounted_fs
    )
