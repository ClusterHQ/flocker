# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""Unit tests for ZFS filesystem implementation.

Further coverage is provided in
:module:`flocker.volume.functional.test_filesystems_zfs`.
"""

import os
from datetime import datetime

from pytz import UTC

from twisted.trial.unittest import SynchronousTestCase
from twisted.internet.error import ProcessDone, ProcessTerminated
from twisted.python.failure import Failure

from ...testtools import FakeProcessReactor

from ..snapshots import SnapshotName
from ..filesystems.zfs import (
    zfs_command, CommandFailed, BadArguments, Filesystem, ZFSSnapshots,
    )


class FilesystemTests(SynchronousTestCase):
    """
    Tests for :class:`Filesystem`.
    """
    def test_name(self):
        """
        ``Filesystem.name`` returns the ZFS filesystem name,
        (``pool/dataset``).
        """
        filesystem = Filesystem(b"hpool", b"mydataset")
        self.assertEqual(filesystem.name, b"hpool/mydataset")

    def test_root_name(self):
        """Given dataset ``None``, ``Filesystem.name`` returns the ZFS
        filesystem name which is just the pool name.
        """
        filesystem = Filesystem(b"hpool", None)
        self.assertEqual(filesystem.name, b"hpool")


class ZFSCommandTests(SynchronousTestCase):
    """
    Tests for :func:`zfs_command`.
    """
    def test_call(self):
        """A ``zfs`` subprocess is launched with the given arguments."""
        reactor = FakeProcessReactor()
        zfs_command(reactor, [b"-H", b"lalala"])
        arguments = reactor.processes[0]
        self.assertEqual((arguments.executable, arguments.args, arguments.env),
                         (b"zfs", [b"zfs", b"-H", b"lalala"], os.environ))

    def test_normal_exit(self):
        """If the subprocess exits with exit code 0, the bytes output by its
        stdout are returned as the result of the ``Deferred`` returned from
        ``zfs_command``.
        """
        reactor = FakeProcessReactor()
        result = zfs_command(reactor, [b"-H", b"lalala"])
        process_protocol = reactor.processes[0].processProtocol
        process_protocol.childDataReceived(1, b"abc")
        process_protocol.childDataReceived(1, b"def")
        process_protocol.processEnded(Failure(ProcessDone(0)))
        self.assertEqual(self.successResultOf(result), b"abcdef")

    def test_error_exit(self):
        """If the subprocess exits with exit code 1, the ``Deferred`` returned
        from ``zfs_command`` errbacks with ``CommandFailed``.
        """
        reactor = FakeProcessReactor()
        result = zfs_command(reactor, [b"-H", b"lalala"])
        process_protocol = reactor.processes[0].processProtocol
        process_protocol.processEnded(Failure(ProcessTerminated(1)))
        self.failureResultOf(result, CommandFailed)

    def test_bad_arguments_exit(self):
        """If the subprocess exits with exit code 2, the ``Deferred`` returned
        from ``zfs_command`` errbacks with ``BadArguments``.
        """
        reactor = FakeProcessReactor()
        result = zfs_command(reactor, [b"-H", b"lalala"])
        process_protocol = reactor.processes[0].processProtocol
        process_protocol.processEnded(Failure(ProcessTerminated(2)))
        self.failureResultOf(result, BadArguments)

    def test_other_exit(self):
        """
        If the subprocess exits with exit code other than 0, 1 or 2, the
        ``Deferred`` returned from ``zfs_command`` errbacks with
        whatever error the process exited with.
        """
        reactor = FakeProcessReactor()
        result = zfs_command(reactor, [b"-H", b"lalala"])
        process_protocol = reactor.processes[0].processProtocol
        exception = ProcessTerminated(99)
        process_protocol.processEnded(Failure(exception))
        self.assertEqual(self.failureResultOf(result).value, exception)


class ZFSSnapshotsTests(SynchronousTestCase):
    """Unit tests for ``ZFSSnapshotsTests``."""

    def test_create(self):
        """
        ``ZFSSnapshots.create()`` calls the ``zfs snapshot`` command with the
        filesystem and snapshot name.
        """
        reactor = FakeProcessReactor()
        snapshots = ZFSSnapshots(reactor, Filesystem(b"mypool", "fs"))
        name = SnapshotName(datetime.now(UTC), b"node")
        snapshots.create(name)
        arguments = reactor.processes[0]
        self.assertEqual(arguments.args, [b"zfs", b"snapshot",
                                          b"mypool/fs@%s" % (name.to_bytes(),)])

    def test_create_no_result_yet(self):
        """
        The result of ``ZFSSnapshots.create()`` is a ``Deferred`` that does not
        fire if the creation is unfinished.
        """
        reactor = FakeProcessReactor()
        snapshots = ZFSSnapshots(reactor, Filesystem(b"mypool", None))
        d = snapshots.create(SnapshotName(datetime.now(UTC), b"node"))
        self.assertNoResult(d)

    def test_create_result(self):
        """
        The result of ``ZFSSnapshots.create()`` is a ``Deferred`` that fires
        when creation has finished.
        """
        reactor = FakeProcessReactor()
        snapshots = ZFSSnapshots(reactor, Filesystem(b"mypool", None))
        d = snapshots.create(SnapshotName(datetime.now(UTC), b"node"))
        reactor.processes[0].processProtocol.processEnded(
            Failure(ProcessDone(0)))
        self.assertEqual(self.successResultOf(d), None)

    def test_list(self):
        """
        ``ZFSSnapshots.list()`` calls the ``zfs list`` command with the pool
        name.
        """
        reactor = FakeProcessReactor()
        snapshots = ZFSSnapshots(reactor, Filesystem(b"mypool", None))
        snapshots.list()
        self.assertEqual(reactor.processes[0].args,
                         [b"zfs", b"list", b"-H", b"-r", b"-t", b"snapshot",
                          b"-o", b"name", b"-s", b"name", b"mypool"])

    def test_list_result(self):
        """
        ``ZFSSnapshots.list`` parses out the snapshot names from the results of
        the command.
        """
        reactor = FakeProcessReactor()
        snapshots = ZFSSnapshots(reactor, Filesystem(b"mypool", None))
        name = SnapshotName(datetime.now(UTC), b"node")
        name2 = SnapshotName(datetime.now(UTC), b"node2")

        d = snapshots.list()
        process_protocol = reactor.processes[0].processProtocol
        process_protocol.childDataReceived(
            1, b"mypool@%s\n" % (name.to_bytes(),))
        process_protocol.childDataReceived(
            1, b"mypool@%s\n" % (name2.to_bytes(),))
        reactor.processes[0].processProtocol.processEnded(
            Failure(ProcessDone(0)))
        self.assertEqual(self.successResultOf(d), [name, name2])

    def test_list_result_ignores_other_pools(self):
        """
        ``ZFSSnapshots.list`` skips snapshots of other pools.

        In particular, we are likely to see snapshot names of sub-pools in
        the output.
        """
        reactor = FakeProcessReactor()
        snapshots = ZFSSnapshots(reactor, Filesystem(b"mypool", None))
        name = SnapshotName(datetime.now(UTC), b"node")
        name2 = SnapshotName(datetime.now(UTC), b"node2")

        d = snapshots.list()
        process_protocol = reactor.processes[0].processProtocol
        process_protocol.childDataReceived(
            1, b"mypool/child@%s\n" % (name.to_bytes(),))
        process_protocol.childDataReceived(
            1, b"mypool@%s\n" % (name2.to_bytes(),))
        reactor.processes[0].processProtocol.processEnded(
            Failure(ProcessDone(0)))
        self.assertEqual(self.successResultOf(d), [name2])

    def test_list_ignores_undecodable_snapshots(self):
        """
        ``ZFSSnapshots.list`` skips snapshots whose names cannot be decoded.

        These are presumably snapshots not being managed by Flocker.
        """
        reactor = FakeProcessReactor()
        snapshots = ZFSSnapshots(reactor, Filesystem(b"mypool", None))
        name = SnapshotName(datetime.now(UTC), b"node")

        d = snapshots.list()
        process_protocol = reactor.processes[0].processProtocol
        process_protocol.childDataReceived(1, b"mypool@alalalalal\n")
        process_protocol.childDataReceived(
            1, b"mypool@%s\n" % (name.to_bytes(),))
        reactor.processes[0].processProtocol.processEnded(
            Failure(ProcessDone(0)))
        self.assertEqual(self.successResultOf(d), [name])
