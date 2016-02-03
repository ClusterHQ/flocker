# -*- test-case-name: flocker.node.agents.test.test_shadow_bind_mounter -*-
# Copyright ClusterHQ Inc.  See LICENSE file for details.

from pyrsistent import PClass, field

from .blockdevice_manager import (
    MountInfo, Permissions, SystemFileLocation,
)


def create_tmpfs_shadow_mount(backing_directory, read_only_directory,
                              blockdevice_manager):
    """
    Creates a "shadow mount directory". This is a tmpfs mount that is bind
    mounted read-only to another location. The intent is to have the following
    characteristics:

        - The read_only_directory is cleared on reboots. Since flocker manually
            mounts volumes rather than changing fstab, the volumes will not be
            remounted by the system on reboot, so mountpoints should also be
            cleaned up on reboot.
        - The read_only_directory can be changed only by agents that know the
            path of the backing directory. This makes it so that clients of
            flocker cannot create paths and start using them before or after
            flocker has the backing volume mounted at a location.

    :param FilePath backing_directory: The directory that backs the shadow
        mount. Will be created if it does not exist. This will be read write.
    :param FilePath read_only_directory: The read only directory of the shadow
        mount. Will be created if it does not exist.
    :param IBlockDeviceManager blockdevice_manager: The provider of
        :class:`IBlockDeviceManager` to use to create the shadow mount.
    """
    if not backing_directory.exists():
        backing_directory.makedirs()
    blockdevice_manager.make_tmpfs_mount(backing_directory)
    blockdevice_manager.share_mount(backing_directory)
    blockdevice_manager.remount(backing_directory, Permissions.READ_ONLY)
    if not read_only_directory.exists():
        read_only_directory.makedirs()
    blockdevice_manager.bind_mount(backing_directory, read_only_directory)
    blockdevice_manager.remount(backing_directory, Permissions.READ_WRITE)


def _is_ancestor(candidate_ancestor, path):
    """
    Determines if a canidate ancestor path is an ancestor to the given path.

    :param FilePath candidate_ancestor: The ancestor path to inquire about.
    :param FilePath path: The descendent  path to inquire about.

    :returns bool: Whether path is a descendent (or equal to)
        candidate_ancestor.
    """
    if candidate_ancestor == path:
        return True
    try:
        path.segmentsFrom(candidate_ancestor)
    except ValueError:
        return False
    else:
        return True


class _DirInfo(PClass):
    """
    Helper utility for holding the :class:`SystemFileLocation` location of a
    directory and the :class:`MountInfo` of the mount that it is under.

    :ivar system_file_location: The :class:`SystemFileLocation` of the
        directory.
    :ivar mount_info: Detailed information about the mount the directory is
        located within.
    """
    system_file_location = field(type=SystemFileLocation, mandatory=True)
    mount_info = field(type=MountInfo, mandatory=True)


def _get_dir_info_for_dir_in_mount(file_path, mount_info):
    """
    Determines the :class:`_DirInfo` of ``file_path`` assuming that it is
    within the mount ``mount_info`` or returns ``None``.

    :param FilePath file_path: The file path to determine the
        :class:`_DirInfo` of.
    :param FilePath file_path: The file path to determine the
        :class:`_DirInfo` of.
    """
    if _is_ancestor(mount_info.mountpoint, file_path):
        if file_path == mount_info.mountpoint:
            segments = []
        else:
            segments = file_path.segmentsFrom(mount_info.mountpoint)
        root_location = mount_info.root_location
        dev_path = reduce(lambda p, c: p.child(c),
                          segments, root_location.path)
        return _DirInfo(
            system_file_location=root_location.set('path', dev_path),
            mount_info=mount_info
        )
    return None


def is_shadow_mount(backing_directory, read_only_directory,
                    blockdevice_manager):
    """
    Detects if there exists a shadow mount from ``backing_directory`` to
    ``read_only_directory`.

    :param FilePath backing_directory: The candidate directory that backs the
        shadow mount.
    :param FilePath read_only_directory: The candidate read only directory of
        the shadow mount. Will be created if it does not exist.
    :param IBlockDeviceManager blockdevice_manager: The provider of
        :class:`IBlockDeviceManager` to use to verify the shadow mount.

    :returns bool: Whether there is a shadow mount from ``backing_directory``
        to  ``read_only_directory``.
    """
    if not backing_directory.isdir():
        return False
    if not read_only_directory.isdir():
        return False
    mounts = blockdevice_manager.get_all_mounts()
    read_only_dir_info = None
    backing_dir_info = None
    # Parse the mounts in reverse order. Most recent mounts are at the bottom,
    # and mounts are resolved from most recent to least recent.
    for mount in reversed(mounts):
        if not read_only_dir_info:
            read_only_dir_info = _get_dir_info_for_dir_in_mount(
                read_only_directory, mount)
        if not backing_dir_info:
            backing_dir_info = _get_dir_info_for_dir_in_mount(
                backing_directory, mount)
        if read_only_dir_info and backing_dir_info:
            break
    return (read_only_dir_info.system_file_location ==
            backing_dir_info.system_file_location and
            read_only_dir_info.mount_info.permissions == Permissions.READ_ONLY)
