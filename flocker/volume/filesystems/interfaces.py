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
    """A filesystem that is part of a pool."""

    def get_mountpoint():
        """Retrieve the filesystem mount point.

        :return: The mountpoint as a ``FilePath``.
        """

    def set_mountpoint(path):
        """Set a new mount point, or unmount the filesystem.

        :param path: The mountpoint as a ``FilePath``, or ``None`` to
            unmount the filesystem.

        :return: A Deferred that fires when the mount point has been changed.
        """


class IStoragePool(Interface):
    """Pool of on-disk storage where filesystems are stored."""

    def create(volume):
        """Create a new unmounted filesystem for the given volume.

        :param volume: The volume whose filesystem should be created.
        :type volume: XXX.

        :return: Deferred that fires on filesystem creation with a
            :class:`IFilesystem` provider, or errbacks if creation failed.
        """

    def get(volume):
        """Return a filesystem object for the given volume.

        :param volume: The volume whose filesystem is being retrieved.
        :type volume: XXX.

        :return: Deferred that fires with a :class:`IFilesystem` provider,
            or errbacks with ``KeyError`` if the filesystem does not exit.
        """
