"""
Drive the snapshotting of a filesystem, based on change events from elsewhere.
"""

from __future__ import absolute_import


class ChangeSnapshotter(object):
    """
    Create snapshots based on writes to a filesystem.

    1. All changes to the filesystem should result in a snapshot being
       created in the near future.
    2. Only one snapshot should be created at a time (i.e. no parallel
       snapshots).
    3. Snapshots are named using the current time and the node they were
       created on.
    4. Snapshots are expected to run very quickly, so if a snapshot take
       more than 10 seconds it should be cancelled.

    This suggests the following state machine, (input, state) -> outputs, new_state:

    (FILESYSTEM_CHANGE, IDLE) -> [START_SNAPSHOT], SNAPSHOTTING
    (FILESYSTEM_CHANGE, SNAPSHOTTING) -> [], SNAPSHOTTING_DIRTY
    (FILESYSTEM_CHANGE, SNAPSHOTTING_DIRTY) -> [], SNAPSHOTTING_DIRTY
    (SNAPSHOT_SUCCESS, SNAPSHOTTING) -> IDLE
    (SNAPSHOT_SUCCESS, SNAPSHOTTING_DIRTY) -> [START_SNAPSHOT], SNAPSHOTTING
    (SNAPSHOT_FAILURE, SNAPSHOTTING) -> [START_SNAPSHOT], SNAPSHOTTING
    (SNAPSHOT_FAILURE, SNAPSHOTTING_DIRTY) -> [START_SNAPSHOT], SNAPSHOTTING

    output_START_SNAPSHOT should create the snapshot, and add a 10 second timeout to the Deferred.

    As a second pass we probably want to wait 1 second between snapshots:
    https://www.pivotaltracker.com/n/projects/1069998/stories/70790540

    Obvious reasons for snapshot failing:
    * Disk is full. This will be handled by
      https://www.pivotaltracker.com/n/projects/1069998/stories/70790286
    * Snapshotting took too long so it was cancelled.
    """
    def __init__(self, name, clock, fsSnapshots):
        """
        :param name: The name of the current node, to be used in snapshot names.
        :type name: bytes

        :param clock: A IReactorTime provider.

        :param fsSnapshots: A IFilesystemSnapshots provider.
        """


    def changeHappened(self):
        """
        Notification from some external entity that the filesystem has changed.
        """
