# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Unit tests for ZFS filesystem implementation.

Further coverage is provided in
:module:`flocker.functional.test_filesystems_zfs`.
"""

import os
from datetime import datetime

from pytz import UTC

from twisted.trial.unittest import SynchronousTestCase
from twisted.internet.error import ProcessDone, ProcessTerminated
from twisted.python.failure import Failure

from .utils import FakeProcessReactor

from ..snapshots import SnapshotName
from ..filesystems.zfs import (
    zfsCommand, CommandFailed, BadArguments, Filesystem, ZFSSnapshots,
    )


class ZfsCommandTests(SynchronousTestCase):
    """
    Tests for :func:`zfsCommand`.
    """
    def test_call(self):
        """
        A ``zfs`` subprocess is launched with the given arguments.
        """
        reactor = FakeProcessReactor()
        zfsCommand(reactor, [b"-H", b"lalala"])
        arguments = reactor.processes[0]
        self.assertEqual((arguments.executable, arguments.args, arguments.env),
                         (b"zfs", [b"zfs", b"-H", b"lalala"], os.environ))


    def test_normalExit(self):
        """
        If the subprocess exits with exit code 0, the bytes output by its stdout
        are returned as the result of the ``Deferred`` returned from
        ``zfsCommand``.
        """
        reactor = FakeProcessReactor()
        result = zfsCommand(reactor, [b"-H", b"lalala"])
        processProtocol = reactor.processes[0].processProtocol
        processProtocol.childDataReceived(1, b"abc")
        processProtocol.childDataReceived(1, b"def")
        processProtocol.processEnded(Failure(ProcessDone(0)))
        self.assertEqual(self.successResultOf(result), b"abcdef")


    def test_errorExit(self):
        """
        If the subprocess exits with exit code 1, the ``Deferred`` returned from
        ``zfsCommand`` errbacks with ``CommandFailed``.
        """
        reactor = FakeProcessReactor()
        result = zfsCommand(reactor, [b"-H", b"lalala"])
        processProtocol = reactor.processes[0].processProtocol
        processProtocol.processEnded(Failure(ProcessTerminated(1)))
        self.failureResultOf(result, CommandFailed)


    def test_badArgumentsExit(self):
        """
        If the subprocess exits with exit code 2, the ``Deferred`` returned from
        ``zfsCommand`` errbacks with ``BadArguments``.
        """
        reactor = FakeProcessReactor()
        result = zfsCommand(reactor, [b"-H", b"lalala"])
        processProtocol = reactor.processes[0].processProtocol
        processProtocol.processEnded(Failure(ProcessTerminated(2)))
        self.failureResultOf(result, BadArguments)


    def test_otherExit(self):
        """
        If the subprocess exits with exit code other than 0, 1 or 2, the
        ``Deferred`` returned from ``zfsCommand`` errbacks with
        whatever error the process exited with.
        """
        reactor = FakeProcessReactor()
        result = zfsCommand(reactor, [b"-H", b"lalala"])
        processProtocol = reactor.processes[0].processProtocol
        exception = ProcessTerminated(99)
        processProtocol.processEnded(Failure(exception))
        self.assertEqual(self.failureResultOf(result).value, exception)



class ZFSSnapshotsTests(SynchronousTestCase):
    """
    Unit tests for ``ZFSSnapshotsTests``.
    """
    def test_create(self):
        """
        ``ZFSSnapshots.create()`` calls the ``zfs snapshot`` command with the
        pool and snapshot name.
        """
        reactor = FakeProcessReactor()
        snapshots = ZFSSnapshots(reactor, Filesystem(b"mypool"))
        name = SnapshotName(datetime.now(UTC), b"node")
        snapshots.create(name)
        arguments = reactor.processes[0]
        self.assertEqual(arguments.args, [b"zfs", b"snapshot",
                                          b"mypool@%s" % (name.toBytes(),)])


    def test_createNoResultYet(self):
        """
        The result of ``ZFSSnapshots.create()`` is a ``Deferred`` that does not
        fire if the creation is unfinished.
        """
        reactor = FakeProcessReactor()
        snapshots = ZFSSnapshots(reactor, Filesystem(b"mypool"))
        d = snapshots.create(SnapshotName(datetime.now(UTC), b"node"))
        self.assertNoResult(d)


    def test_createResult(self):
        """
        The result of ``ZFSSnapshots.create()`` is a ``Deferred`` that fires
        when creation has finished.
        """
        reactor = FakeProcessReactor()
        snapshots = ZFSSnapshots(reactor, Filesystem(b"mypool"))
        d = snapshots.create(SnapshotName(datetime.now(UTC), b"node"))
        reactor.processes[0].processProtocol.processEnded(
            Failure(ProcessDone(0)))
        self.assertEqual(self.successResultOf(d), None)


    def test_list(self):
        """
        ``ZFSSnapshots.create()`` calls the ``zfs list`` command with the pool
        name.
        """


    def test_listResult(self):
        """
        ``ZFSSnapshots.list`` parses out the snapshot names from the results of
        the command.
        """


    def test_listResultIgnoresOtherPools(self):
        """
        ``ZFSSnapshots.list`` skips snapshots of other pools.

        In particular, we are likely to see snapshot names of sub-pools in
        the output.
        """


    def test_listIgnoresUndecodableSnapshots(self):
        """
        ``ZFSSnapshots.list`` skips snapshots whose names cannot be decoded.

        These are presumably snapshots not being managed by Flocker.
        """
