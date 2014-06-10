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

    def __eq__(other):
        """True if and only if underlying OS filesystem is the same."""

    def __ne__(other):
        """True if and only if underlying OS filesystem is different."""

    def __hash__():
        """Equal objects should have the same hash."""


class IStoragePool(Interface):
    """Pool of on-disk storage where filesystems are stored."""

    def create(volume):
        """Create a new filesystem for the given volume.

        By default new filesystems will be automounted. In future
        iterations when remotely owned filesystems are added
        (https://github.com/hybridlogic/flocker/issues/16) this interface
        will be expanded to allow specifying that the filesystem should
        not be mounted.

        :param volume: The volume whose filesystem should be created.
        :type volume: :class:`flocker.volume.service.Volume`

        :return: Deferred that fires on filesystem creation with a
            :class:`IFilesystem` provider, or errbacks if creation failed.
        """

    def get(volume):
        """Return a filesystem object for the given volume.

        This presumes the volume exists.

        :param volume: The volume whose filesystem is being retrieved.
        :type volume: :class:`flocker.volume.service.Volume`

        :return: A :class:`IFilesystem` provider.
        """

    def enumerate():
        """Get a listing of all volumes in this pool.

        :return: A ``Deferred`` that fires with a :class:`list` of
            :class:`Volume` instances.
        """
