"""
Snapshotting of a filesystem.
"""

from zope.interface import Interface


class IFilesystemSnapshots(Interface):
    """
    Support creating and listing snapshots of a specific filesystem.
    """
    def create(name):
        """
        Create a snapshot of the filesystem.

        @param name: The name of the snapshot.
        @type name: L{bytes}

        @return: L{Deferred} that fires on snapshot creation, or errbacks if
            snapshotting failed.
        """


    def list():
        """
        Return all the filesystem's snapshots.

        @return: L{Deferred} that fires with a L{list} of L{bytes} (snapshot
            names). This will likely be improved in later iterations.
        """



class ChangeSnapshotter(object):
    """
    Create snapshots based on writes to a filesystem.

    1. All changes to the filesystem should result in a snapshot being
       created in the near future.
    2. Only one snapshot should be created at a time (i.e. no parallel
       snapshots).
    3. Snapshots are named using the current time and the node they were
       created on.

    This suggests the following state machine, (input, state) -> new_state:

    (FILESYSTEM_CHANGE, IDLE) -> SNAPSHOTTING
    (FILESYSTEM_CHANGE, SNAPSHOTTING) -> SNAPSHOTTING_DIRTY
    (FILESYSTEM_CHANGE, SNAPSHOTTING_DIRTY) -> SNAPSHOTTING_DIRTY
    (SNAPSHOT_SUCCESS, SNAPSHOTTING) -> IDLE
    (SNAPSHOT_SUCCESS, SNAPSHOTTING_DIRTY) -> SNAPSHOTTING
    (SNAPSHOT_FAILURE, SNAPSHOTTING) -> SNAPSHOTTING
    (SNAPSHOT_FAILURE, SNAPSHOTTING_DIRTY) -> SNAPSHOTTING

    (As a second pass we probably want to wait 1 second between snapshots.)
    """
    def __init__(self, name, clock, fsSnapshots):
        """
        @param name: The name of the current node, to be used in snapshot names.
        @type name: L{bytes}

        @param clock: A L{IReactorTime} provider.

        @param fsSnapshots: A L{IFilesystemSnapshots} provider.
        """
