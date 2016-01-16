# -*- test-case-name: flocker.node.agents.test.test_shadow_bind_mounter -*-
# Copyright ClusterHQ Inc.  See LICENSE file for details.

from .blockdevice_manager import Permissions


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
