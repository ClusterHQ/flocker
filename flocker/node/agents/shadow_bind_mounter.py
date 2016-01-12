# -*- test-case-name: flocker.node.agents.test.test_shadow_bind_mounter -*-
# Copyright ClusterHQ Inc.  See LICENSE file for details.

from .blockdevice_manager import Permissions


def create_tmpfs_shadow_mount(backing_directory, read_only_directory,
                              blockdevice_manager):
    """
    Creates a "shadow mount directory". This is a tmpfs mount that is bind
    mounted read-only to another location. The intent is to have the following
    characteristics:

        - The read_only_directory is cleared on reboots.
        - The read_only_directory can be changed only by agents that know the
            path of the backing directory.

    :param FilePath backing_directory: The directory that will be created if
        need be to back the shadow mount. This will be read write.
    :param FilePath read_only_directory: The read_only_directory that will have
        to be bind mounted to the backing
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
