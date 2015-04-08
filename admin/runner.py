# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
"""
Tools for running commands.
"""
import sys
import os

from characteristic import attributes

from twisted.internet.error import ConnectionDone
from twisted.internet.endpoints import ProcessEndpoint, connectProtocol
from twisted.internet.defer import Deferred

from twisted.protocols.basic import LineOnlyReceiver


@attributes([
    "deferred",
    "output",
])
class CommandProtocol(LineOnlyReceiver, object):
    """
    Protocol that logs the lines of a remote command.

    :ivar Deferred deferred: Deferred to fire when the command finishes
        If the command finished succesfuly, will fire with ``None``.
        Otherwise, errbacks with the reason.
    :ivar file-like output: For logging.
    """
    delimiter = b'\n'

    def connectionMade(self):
        self.transport.disconnecting = False

    def connectionLost(self, reason):
        if reason.check(ConnectionDone):
            self.deferred.callback(None)
        else:
            self.deferred.errback(reason)

    def lineReceived(self, line):
        self.output.write(line + "\n")


def run(reactor, command, **kwargs):
    if 'env' not in kwargs:
        kwargs['env'] = os.environ
    endpoint = ProcessEndpoint(reactor, command[0], command, **kwargs)
    protocol_done = Deferred()
    protocol = CommandProtocol(deferred=protocol_done, output=sys.stdout)

    connected = connectProtocol(endpoint, protocol)

    def unregister_killer(result, trigger_id):
        reactor.removeSystemEventTrigger(trigger_id)
        return result

    def register_killer(_):
        trigger_id = reactor.addSystemEventTrigger(
            'before', 'shutdown', protocol.transport.signalProcess, 'TERM')
        protocol_done.addBoth(unregister_killer, trigger_id)
        pass

    connected.addCallback(register_killer)
    connected.addCallback(lambda _: protocol_done)
    return connected
