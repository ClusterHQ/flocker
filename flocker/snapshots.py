"""
Drive the snapshotting of a filesystem, based on change events from elsewhere.
"""

from __future__ import absolute_import

from collections import namedtuple
from datetime import datetime

from pytz import UTC

from twisted.python.constants import Names, NamedConstant

from machinist import (
    TransitionTable, MethodSuffixOutputer, constructFiniteStateMachine,
    trivialInput)



class SnapshotName(namedtuple("SnapshotName", "timestamp node")):
    """
    A name of a snapshot.

    :attr timestamp: The time when the snapshot was created, a :class:`datetime`.

    :attr node: The name of the node creating the snapshot, as ``bytes``.
    """



class _Inputs(Names):
    """
    Inputs to the ChangeSnapshotter state machine.
    """
    FILESYSTEM_CHANGED = NamedConstant()
    SNAPSHOT_SUCCEEDED = NamedConstant()
    SNAPSHOT_FAILED = NamedConstant()

FILESYSTEM_CHANGED = trivialInput(_Inputs.FILESYSTEM_CHANGED)
SNAPSHOT_SUCCEEDED = trivialInput(_Inputs.SNAPSHOT_SUCCEEDED)
SNAPSHOT_FAILED = trivialInput(_Inputs.SNAPSHOT_FAILED)



class _Outputs(Names):
    """
    Outputs from the ChangeSnapshotter state machine.
    """
    START_SNAPSHOT = NamedConstant()



class _States(Names):
    """
    States of the ChangeSnapshotter state machine.
    """
    IDLE = NamedConstant()
    SNAPSHOTTING = NamedConstant()
    #: The filesystem changed *after* the snapshot was started:
    SNAPSHOTTING_DIRTY = NamedConstant()



_doSnapshot = ([_Outputs.START_SNAPSHOT], _States.SNAPSHOTTING)

_transitions = TransitionTable()
_transitions = _transitions.addTransitions(
    _States.IDLE, {
        _Inputs.FILESYSTEM_CHANGED: _doSnapshot,
        })
_transitions = _transitions.addTransitions(
    _States.SNAPSHOTTING, {
        _Inputs.FILESYSTEM_CHANGED: ([], _States.SNAPSHOTTING_DIRTY),
        _Inputs.SNAPSHOT_SUCCEEDED: ([], _States.IDLE),
        _Inputs.SNAPSHOT_FAILED: _doSnapshot,
    })
_transitions = _transitions.addTransitions(
    _States.SNAPSHOTTING_DIRTY, {
        _Inputs.FILESYSTEM_CHANGED: ([], _States.SNAPSHOTTING_DIRTY),
        _Inputs.SNAPSHOT_SUCCEEDED: _doSnapshot,
        _Inputs.SNAPSHOT_FAILED: _doSnapshot,
    })



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
        self._name = name
        self._clock = clock
        self._fsSnapshots = fsSnapshots
        self._fsm = constructFiniteStateMachine(
            inputs=_Inputs, outputs=_Outputs, states=_States, table=_transitions,
            initial=_States.IDLE,
            richInputs=[FILESYSTEM_CHANGED, SNAPSHOT_SUCCEEDED, SNAPSHOT_FAILED],
            inputContext={}, world=MethodSuffixOutputer(self))


    def output_START_SNAPSHOT(self, context):
        name = SnapshotName(datetime.fromtimestamp(self._clock.seconds(), UTC),
                            self._name)
        created = self._fsSnapshots.create(name)
        # XXX log errors!
        # https://www.pivotaltracker.com/n/projects/1069998/stories/70956276
        created.addCallbacks(lambda _: self._fsm.receive(SNAPSHOT_SUCCEEDED()),
                             lambda _: self._fsm.receive(SNAPSHOT_FAILED()))


    def filesystemChanged(self):
        """
        Notification from some external entity that the filesystem has changed.
        """
        self._fsm.receive(FILESYSTEM_CHANGED())
