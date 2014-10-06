# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""Unit tests for ZFS filesystem implementation.

Further coverage is provided in
:module:`flocker.volume.functional.test_filesystems_zfs`.
"""

import os

from twisted.trial.unittest import SynchronousTestCase
from twisted.internet.error import ProcessDone, ProcessTerminated
from twisted.python.failure import Failure

from eliot import Logger
from eliot.testing import LoggedMessage, validateLogging, assertContainsFields

from ...testtools import FakeProcessReactor

from ..filesystems.zfs import (
    zfs_command, CommandFailed, BadArguments, Filesystem, ZFSSnapshots,
    _sync_command_error_squashed, _latest_common_snapshot, ZFS_ERROR,
    Snapshot,
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


def no_such_executable_logged(case, logger):
    """
    Validate the error logging behavior of ``_sync_command_error_squashed``.
    """
    errors = LoggedMessage.ofType(logger.messages, ZFS_ERROR)
    assertContainsFields(
        case, errors[0].message,
        {'status': 1,
         'zfs_command': 'nonsense garbage made up no such command',
         'output': '[Errno 2] No such file or directory',
         u'message_type': 'filesystem:zfs:error',
         u'task_level': u'/'})
    case.assertEqual(1, len(errors))


def error_status_logged(case, logger):
    """
    Validate the error logging behavior of ``_sync_command_error_squashed``.
    """
    errors = LoggedMessage.ofType(logger.messages, ZFS_ERROR)
    assertContainsFields(
        case, errors[0].message,
        {'status': 1,
         'zfs_command': 'python -c raise SystemExit(1)',
         'output': '',
         u'message_type': 'filesystem:zfs:error',
         u'task_level': u'/'})
    case.assertEqual(1, len(errors))


class SyncCommandTests(SynchronousTestCase):
    """
    Tests for ``_sync_command_error_squashed``.
    """
    @validateLogging(no_such_executable_logged)
    def test_no_such_executable(self, logger):
        """
        If the executable specified to ``_sync_command_error_squashed`` cannot
        be found then the function nevertheless returns ``None``.
        """
        result = _sync_command_error_squashed(
            [b"nonsense garbage made up no such command"],
            logger)
        self.assertIs(None, result)

    @validateLogging(error_status_logged)
    def test_error_exit(self, logger):
        """
        If the child process run by ``_sync_command_error_squashed`` exits with
        an an error status then the function nevertheless returns ``None``.
        """
        result = _sync_command_error_squashed(
            [b"python", b"-c", b"raise SystemExit(1)"],
            logger)
        self.assertIs(None, result)

    def test_success(self):
        """
        ``_sync_command_error_squashed`` runs the given command and returns
        ``None``.
        """
        result = _sync_command_error_squashed(
            [b"python", b"-c", b""],
            Logger())
        self.assertIs(None, result)


class ZFSSnapshotsTests(SynchronousTestCase):
    """Unit tests for ``ZFSSnapshotsTests``."""

    def test_create(self):
        """
        ``ZFSSnapshots.create()`` calls the ``zfs snapshot`` command with the
        given ``bytes`` as the snapshot name.
        """
        reactor = FakeProcessReactor()
        snapshots = ZFSSnapshots(reactor, Filesystem(b"pool", "fs"))
        snapshots.create(b"myname")
        arguments = reactor.processes[0]
        self.assertEqual(arguments.args, [b"zfs", b"snapshot",
                                          b"pool/fs@myname"])

    def test_create_no_result_yet(self):
        """
        The result of ``ZFSSnapshots.create()`` is a ``Deferred`` that does not
        fire if the creation is unfinished.
        """
        reactor = FakeProcessReactor()
        snapshots = ZFSSnapshots(reactor, Filesystem(b"mypool", None))
        d = snapshots.create(b"name")
        self.assertNoResult(d)

    def test_create_result(self):
        """
        The result of ``ZFSSnapshots.create()`` is a ``Deferred`` that fires
        when creation has finished.
        """
        reactor = FakeProcessReactor()
        snapshots = ZFSSnapshots(reactor, Filesystem(b"mypool", None))
        d = snapshots.create(b"name")
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
                          b"-o", b"name", b"-s", b"creation", b"mypool"])

    def test_list_result_root_dataset(self):
        """
        ``ZFSSnapshots.list`` parses out the snapshot names of the root dataset
        from the results of the command.
        """
        reactor = FakeProcessReactor()
        snapshots = ZFSSnapshots(reactor, Filesystem(b"mypool", None))

        d = snapshots.list()
        process_protocol = reactor.processes[0].processProtocol
        process_protocol.childDataReceived(1, b"mypool@name\n")
        process_protocol.childDataReceived(1, b"mypool@name2\n")
        reactor.processes[0].processProtocol.processEnded(
            Failure(ProcessDone(0)))
        self.assertEqual(self.successResultOf(d), [b"name", b"name2"])

    def test_list_result_child_dataset(self):
        """
        ``ZFSSnapshots.list`` parses out the snapshot names of a non-root
        dataset from the results of the command.
        """
        reactor = FakeProcessReactor()
        snapshots = ZFSSnapshots(reactor, Filesystem(b"mypool", b"myfs"))

        d = snapshots.list()
        process_protocol = reactor.processes[0].processProtocol
        process_protocol.childDataReceived(1, b"mypool/myfs@name\n")
        process_protocol.childDataReceived(1, b"mypool/myfs@name2\n")
        reactor.processes[0].processProtocol.processEnded(
            Failure(ProcessDone(0)))
        self.assertEqual(self.successResultOf(d), [b"name", b"name2"])

    def test_list_result_ignores_other_pools(self):
        """
        ``ZFSSnapshots.list`` skips snapshots of other pools.

        In particular, we are likely to see snapshot names of sub-pools in
        the output.
        """
        reactor = FakeProcessReactor()
        snapshots = ZFSSnapshots(reactor, Filesystem(b"mypool", None))

        d = snapshots.list()
        process_protocol = reactor.processes[0].processProtocol
        process_protocol.childDataReceived(1, b"mypool/child@name\n")
        process_protocol.childDataReceived(1, b"mypool@name2\n")
        reactor.processes[0].processProtocol.processEnded(
            Failure(ProcessDone(0)))
        self.assertEqual(self.successResultOf(d), [b"name2"])


class LatestCommonSnapshotTests(SynchronousTestCase):
    """
    Tests for ``_latest_common_snapshot``.
    """
    def test_no_common(self):
        """
        If there are no common ``Snapshot`` instances in the two ``list``\ s,
        ``_latest_common_snapshot`` returns ``None``.
        """
        self.assertIs(
            None,
            _latest_common_snapshot(
                [Snapshot(name=b"a")], [Snapshot(name=b"b")]))

    def test_empty_list(self):
        """
        If one of the ``list``\ s passed to ``_latest_common_snapshot`` is
        empty, ``None`` is returned.
        """
        self.assertIs(
            None, _latest_common_snapshot([Snapshot(name=b"a")], []))

    def test_last_snapshot_common(self):
        """
        If the last ``Snapshot`` in the ``list``\ s passed to
        ``_latest_common_snapshot`` is the same, it is returned.
        """
        a = Snapshot(name=b"a")
        b = Snapshot(name=b"b")
        c = Snapshot(name=b"c")
        self.assertEqual(
            a, _latest_common_snapshot([b, a], [c, a]))

    def test_earlier_snapshot_common(self):
        """
        If only one ``Snapshot`` is common to the two lists and it appears
        somewhere in the middle, it is returned.
        """
        a = Snapshot(name=b"a")
        b = Snapshot(name=b"b")
        c = Snapshot(name=b"c")
        d = Snapshot(name=b"d")
        e = Snapshot(name=b"e")
        self.assertEqual(
            a, _latest_common_snapshot([b, a, c], [d, a, e]))

    def test_multiple_common(self):
        """
        If multiple ``Snapshot``\ s are common to the two lists, the one which
        appears closest to the end is returned.
        """
        a = Snapshot(name=b"a")
        b = Snapshot(name=b"b")
        self.assertEqual(
            b, _latest_common_snapshot([a, b], [a, b]))
