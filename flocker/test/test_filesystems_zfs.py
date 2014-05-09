# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Unit tests for ZFS filesystem implementation.

Further coverage is provided in
:module:`flocker.functional.test_filesystems_zfs`.
"""

import os

from twisted.trial.unittest import SynchronousTestCase
from twisted.internet.error import ProcessDone, ProcessTerminated
from twisted.python.failure import Failure

from .utils import FakeProcessReactor

from ..filesystems.zfs import zfsCommand, CommandFailed, BadArguments


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
