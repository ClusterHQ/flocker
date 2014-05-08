# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for :module:`flocker.snapshots`.
"""

from __future__ import absolute_import

from datetime import datetime

from pytz import UTC

from twisted.trial.unittest import SynchronousTestCase
from twisted.internet.task import Clock
from twisted.internet.defer import Deferred, succeed

from ..filesystems.memory import MemoryFilesystemSnapshots
from ..snapshots import ChangeSnapshotter, SnapshotName


# The filesystem's name:
FILESYSTEM = b"test"



class ChangeSnapshotterTests(SynchronousTestCase):
    """
    Tests for ChangeSnapshotter state machine.
    """
    def setup(self, results):
        """
        Setup the objects for the test.

        :param results: ``list`` of ``Deferred``, the results of snapshotting.
        """
        self.clock = Clock()
        self.clock.advance(12345)
        self.fsSnapshots = MemoryFilesystemSnapshots(results)
        self.snapshotter = ChangeSnapshotter(FILESYSTEM, self.clock,
                                             self.fsSnapshots)


    def assertSnapshotsTaken(self, snapshotTimes):
        """
        Assert the created snapshots were those described by the given
        parameters.

        :param snapshotTimes: ``list`` of ``float`` describing seconds since
            epoch when snapshots occurred.
        """
        self.assertEqual(
            self.successResultOf(self.fsSnapshots.list()),
            [SnapshotName(datetime.fromtimestamp(t, UTC), FILESYSTEM)
             for t in snapshotTimes])


    def test_idle(self):
        """
        If nothing happens no snapshots are taken.
        """
        self.setup([])
        self.clock.advance(1000)
        self.assertSnapshotsTaken([])


    def test_changeCausesSnapshot(self):
        """
        If :meth:`ChangeSnapshotter.filesystemChanged` is called, a snapshot is
        taken immediately.
        """
        d = Deferred()
        self.setup([d])
        self.snapshotter.filesystemChanged()
        d.callback(None)
        self.assertSnapshotsTaken([self.clock.seconds()])


    def test_successReturnsToInitialState(self):
        """
        If the filesystem changed once, and a snapshot is succesfully taken, the
        state machine returns to its initial state.
        """
        d = Deferred()
        self.setup([d])
        initialState = self.snapshotter._fsm.state
        self.snapshotter.filesystemChanged()
        d.callback(None)
        self.assertEqual(initialState, self.snapshotter._fsm.state)


    def test_retryOnFailure(self):
        """
        If snapshotting fails it is retried until it succeeds.
        """
        fail1, fail2, success = Deferred(), Deferred(), Deferred()
        self.setup([fail1, fail2, success])
        self.snapshotter.filesystemChanged()
        self.clock.advance(1)
        fail1.errback(RuntimeError())
        self.clock.advance(1)
        fail2.errback(RuntimeError())
        success.callback(None)
        # The successful snapshot is the one triggered by the second failure
        # causing a retry:
        self.assertSnapshotsTaken([self.clock.seconds()])


    def test_dirtyFilesystemDuringSnapshot(self):
        """
        If ``filesystemChanged`` is called while a snapshot is in progress,
        another snapshot is not started immediately.
        """
        d = Deferred()
        self.setup([d, succeed(None)])
        self.snapshotter.filesystemChanged()
        # Snapshotting has started, and now another change happens:
        self.snapshotter.filesystemChanged()
        # Only one snapshot started though:
        self.assertEqual(len(self.fsSnapshots._results), 1)


    def test_dirtyFilesystemSchedulesSnapshotOnSuccess(self):
        """
        If ``filesystemChanged`` is called while a snapshot is in progress,
        another snapshot will be done when the first one succeeds.
        """
        first, second = Deferred(), Deferred()
        self.setup([first, second])
        self.snapshotter.filesystemChanged()
        # Snapshotting has started, and now another change happens:
        self.snapshotter.filesystemChanged()
        self.clock.advance(1)
        first.callback(None)
        second.callback(None)
        time = self.clock.seconds()
        self.assertSnapshotsTaken([time - 1, time])


    def test_dirtyFilesystemSchedulesSnapshotOnFailure(self):
        """
        If ``filesystemChanged`` is called while a snapshot is in progress,
        another snapshot will be done when the first one fails.
        """
        first, second = Deferred(), Deferred()
        self.setup([first, second])
        self.snapshotter.filesystemChanged()
        # Snapshotting has started, and now another change happens:
        self.snapshotter.filesystemChanged()
        self.clock.advance(1)
        first.errback(RuntimeError())
        second.callback(None)
        self.assertSnapshotsTaken([self.clock.seconds()])


    def test_filesystemChangesMultipleTimes(self):
        """
        If ``filesystemChanged`` is called multiple times while a snapshot is in
        progress, only one additional snapshot will be done.
        """
        first, second = Deferred(), Deferred()
        self.setup([first, second])
        self.snapshotter.filesystemChanged()
        self.snapshotter.filesystemChanged()
        self.snapshotter.filesystemChanged()
        self.clock.advance(1)
        first.callback(None)
        second.callback(None)
        time = self.clock.seconds()
        self.assertSnapshotsTaken([time - 1, time])


    # If a snapshot takes longer than 10 seconds to finish it will fail.
