# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""Interfaces that filesystem APIs need to expose."""

from __future__ import absolute_import

from zope.interface import Interface


class IFilesystemSnapshots(Interface):
    """Support creating and listing snapshots of a specific filesystem."""

    def create(name):
        """Create a snapshot of the filesystem.

        :param name: The name of the snapshot.
        :type name: :py:class:`flocker.volume.snapshots.SnapshotName`

        :return: Deferred that fires on snapshot creation, or errbacks if
            snapshotting failed. The Deferred should support cancellation
            if at all possible.
        """

    def list():
        """Return all the filesystem's snapshots.

        :return: Deferred that fires with a ``list`` of
            :py:class:`flocker.snapshots.SnapshotName`.
        """


class IFilesystem(Interface):
    """A filesystem.

    - Get the mountpoint as FilePath.
    - Set the mountpoint to path, or None to unmount.
    """



class IStoragePool(Interface):
    """Pool of on-disk storage where filesystems are stored."""

    def create(volume):
        """Create a new unmounted filesystem for the given volume.

        :param volume: The volume whose filesystem should be created.
        :type volume: XXX.

        :return: Deferred that fires on filesystem creation with a XXX, or
            errbacks if creation failed.
        """

    def get(volume):
        """Return a filesystem object for the given volume.

        :param volume: The volume whose filesystem is being retrieved.
        :type volume: XXX.

        :return: Deferred that fires with filesystem XXX, or
            errbacks with ``KeyError`` if the filesystem does not exit.
        """
