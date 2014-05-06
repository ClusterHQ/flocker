"""
Tests for :module:`flocker.snapshots`.
"""
from twisted.trial.unittest import SynchronousTestCase


class ChangeSnapshotterTests(SynchronousTestCase):
    """
    Tests for ChangeSnapshotter.
    """
    # If ``filesystemChanged`` is called, a snapshot is taken immediately.
    # If ``filesystemChanged`` is called once, after a snapshot succeeds no more snapshots are taken.
    # If snapshotting fails, it is retried until it succeeds.
    # If ``filesystemChanged`` is called while a snapshot is in progress, another snapshot is not started immediately.
    # If ``filesystemChanged`` is called while a snapshot is in progress, another snapshot will be done when the first one succeeds.
    # If ``filesystemChanged`` is called while a snapshot is in progress, another snapshot will be done when the first one fails.
    # If ``filesystemChanged`` is called multiple times while a snapshot is in progress, only one additional snapshot will be done.
    # If a snapshot takes longer than 10 seconds to finish it will fail.
