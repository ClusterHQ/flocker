# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
# -*- test-case-name: admin.test.test_runner -*-
"""
Tools for running commands.
"""
import sys
import os
from collections import defaultdict

from characteristic import attributes

from twisted.internet.error import ProcessDone
from twisted.internet.defer import Deferred
from twisted.internet.protocol import ProcessProtocol

from twisted.protocols.basic import LineOnlyReceiver


# LineOnlyReceiver is mutable, so can't use pyrsistent
@attributes([
    "output",
])
class _LineParser(LineOnlyReceiver, object):
    """
    Parser that breaks input into lines, and writes it to ouput.

    :ivar file-like output: For logging.
    """
    delimiter = b'\n'

    def __init__(self):
        self.transport = type('', (object,), {})()
        self.transport.disconnecting = False

    def lineReceived(self, line):
        self.output.write(line + "\n")


@attributes([
    "deferred",
    "output",
])
class CommandProtocol(ProcessProtocol, object):
    """
    Protocol that logs the lines of a remote command.

    :ivar Deferred deferred: Deferred to fire when the command finishes
        If the command finished successfully, will fire with ``None``.
        Otherwise, errbacks with the reason.
    :ivar file-like output: For logging.

    :ivar defaultdict _fds: Mapping from file descriptors to `_LineParsers`.
    """
    def __init__(self):
        self._fds = defaultdict(lambda: _LineParser(output=self.output))

    def childDataReceived(self, childFD, data):
        self._fds[childFD].dataReceived(data)

    def processEnded(self, reason):
        if reason.check(ProcessDone):
            self.deferred.callback(None)
        else:
            self.deferred.errback(reason)


def run(reactor, command, **kwargs):
    """
    Run a process and kill it if the reactor stops.

    :param reactor: Reactor to use.
    :param list command: The command to run.

    :return Deferred: Deferred that fires when the process is ended.
    """
    if 'env' not in kwargs:
        kwargs['env'] = os.environ
    protocol_done = Deferred()
    protocol = CommandProtocol(deferred=protocol_done, output=sys.stdout)

    reactor.spawnProcess(protocol, command[0], command, **kwargs)

    def unregister_killer(result, trigger_id):
        try:
            reactor.removeSystemEventTrigger(trigger_id)
        except:
            # If we can't remove the trigger, presumably it has already been
            # removed (or run). In any case, there is nothing sensible to do
            # if this fails.
            pass
        return result
    trigger_id = reactor.addSystemEventTrigger(
        'before', 'shutdown', protocol.transport.signalProcess, 'TERM')
    protocol_done.addBoth(unregister_killer, trigger_id)

    return protocol_done
