# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""Subprocess helpers"""

from twisted.internet.protocol import Protocol
from twisted.internet.defer import Deferred
from twisted.internet.error import ConnectionDone, ProcessTerminated


class CommandFailed(Exception):
    """The command failed for some reasons."""


class BadArguments(Exception):
    """The command was called with incorrect arguments."""


class _AccumulatingProtocol(Protocol):
    """
    Accumulate all received bytes.
    """

    def __init__(self):
        self._result = Deferred()
        self._data = b""

    def dataReceived(self, data):
        self._data += data

    def connectionLost(self, reason):
        if reason.check(ConnectionDone):
            self._result.callback(self._data)
        elif reason.check(ProcessTerminated) and reason.value.exitCode == 1:
            self._result.errback(CommandFailed())
        elif reason.check(ProcessTerminated) and reason.value.exitCode == 2:
            self._result.errback(BadArguments())
        else:
            self._result.errback(reason)
        del self._result




