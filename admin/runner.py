# -*- test-case-name: admin.test.test_runner -*-
# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
"""
Tools for running commands.
"""
import os

from characteristic import attributes
from eliot import MessageType, ActionType, Field
from eliot.twisted import DeferredContext

from twisted.internet.error import ConnectionDone
from twisted.internet.endpoints import ProcessEndpoint, connectProtocol
from twisted.internet.defer import Deferred

from twisted.protocols.basic import LineOnlyReceiver


RUN_ACTION = ActionType(
    action_type="admin.runner:run",
    startFields=[
        Field.for_types(u"command", [list], u"The command.")
    ],
    successFields=[],
    description="Run a command.",
)
RUN_OUTPUT_MESSAGE = MessageType(
    message_type="admin.runner:run:output",
    fields=[
        Field.for_types(u"line", [bytes], u"The output."),
    ],
    description=u"A line of command output.",
)


# LineOnlyReceiver is mutable, so can't use pyrsistent
@attributes([
    "deferred",
    "action",
])
class CommandProtocol(LineOnlyReceiver, object):
    """
    Protocol that logs the lines of a remote command.

    :ivar Deferred deferred: Deferred to fire when the command finishes
        If the command finished successfully, will fire with ``None``.
        Otherwise, errbacks with the reason.
    :ivar Action action: For logging.
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
        RUN_OUTPUT_MESSAGE(
            line=line,
        ).write(action=self.action)


def run(reactor, command, **kwargs):
    """
    Run a process and kill it if the reactor stops.

    :param reactor: Reactor to use.
    :param list command: The command to run.

    :return Deferred: Deferred that fires when the process is ended.
    """
    if 'env' not in kwargs:
        kwargs['env'] = os.environ

    action = RUN_ACTION(command=command)

    endpoint = ProcessEndpoint(reactor, command[0], command, **kwargs)
    protocol_done = Deferred()
    protocol = CommandProtocol(deferred=protocol_done, action=action)

    with action.context():
        connected = DeferredContext(connectProtocol(endpoint, protocol))

    def unregister_killer(result, trigger_id):
        try:
            reactor.removeSystemEventTrigger(trigger_id)
        except:
            # If we can't remove the trigger, presumably it has already been
            # removed (or run). In any case, there is nothing sensible to do
            # if this fails.
            pass
        return result

    def register_killer(_):
        trigger_id = reactor.addSystemEventTrigger(
            'before', 'shutdown', protocol.transport.signalProcess, 'TERM')
        protocol_done.addBoth(unregister_killer, trigger_id)

    connected.addCallback(register_killer)
    connected.addCallback(lambda _: protocol_done)
    return connected.addActionFinish()
