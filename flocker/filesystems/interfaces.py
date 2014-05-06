"""
Interfaces that filesystem APIs need to expose.
"""
from __future__ import absolute_import

from zope.interface import Interface


class IFilesystemSnapshots(Interface):
    """
    Support creating and listing snapshots of a specific filesystem.
    """
    def create(name):
        """
        Create a snapshot of the filesystem.

        :param name: The name of the snapshot.
        :type name: :py:class:`bytes`

        :return: Deferred that fires on snapshot creation, or errbacks if
            snapshotting failed. The Deferred should support cancellation
            if at all possible.
        """


    def list():
        """
        Return all the filesystem's snapshots.

        :return: Deferred that fires with a ``list`` of ``bytes`` (snapshot
            names). This will likely be improved in later iterations.
        """
