from pipes import quote as shell_quote
from twisted.python import log

from characteristic import attributes

from effect import (
    sync_performer, TypeDispatcher, ComposedDispatcher, Effect,
    )
from effect.twisted import (
    perform, deferred_performer)
from twisted.conch.endpoints import (
    SSHCommandClientEndpoint, _NewConnectionHelper, _ReadFile, ConsoleUI)

from twisted.conch.ssh.keys import Key
from twisted.internet import reactor
from twisted.internet.defer import Deferred, inlineCallbacks
from twisted.internet.endpoints import UNIXClientEndpoint, connectProtocol
from twisted.internet.error import ConnectionDone
from twisted.protocols.basic import LineOnlyReceiver
from twisted.python.filepath import FilePath
import os


@attributes([
    "deferred",
    "address",
    "username",
])
class CommandProtocol(LineOnlyReceiver, object):
    delimiter = b'\n'

    def connectionMade(self):
        self.transport.disconnecting = False

    def connectionLost(self, reason):
        if reason.check(ConnectionDone):
            self.deferred.callback(None)
        else:
            self.deferred.errback(reason)

    def lineReceived(self, line):
        log.msg(format="%(line)s",
                system="SSH[%s@%s]" % (self.username, self.address),
                username=self.username, address=self.address, line=line)


@inlineCallbacks
def run_with_crochet(base_dispatcher, username, address, commands):
    from ._install import Run, Sudo, Put, Comment

    def can_connect():
        import socket
        s = socket.socket()
        conn = s.connect_ex((address, 22))
        return False if conn else True

    from flocker.testtools import loop_until
    yield loop_until(can_connect)

    key_path = FilePath(os.path.expanduser('~/.ssh/id_rsa'))
    if key_path.exists():
        keys = [Key.fromString(key_path.getContent())]
    else:
        keys = None
    try:
        agentEndpoint = UNIXClientEndpoint(
            reactor, os.environ["SSH_AUTH_SOCK"])
    except KeyError:
        agentEndpoint = None
    connection_helper = _NewConnectionHelper(
        reactor, address, 22, None, username,
        keys=keys,
        password=None,
        agentEndpoint=agentEndpoint,
        knownHosts=None, ui=ConsoleUI(lambda: _ReadFile(b"yes")))
    connection = yield connection_helper.secureConnection()

    def do_remote(endpoint):
        d = Deferred()
        return connectProtocol(
            endpoint, CommandProtocol(
                deferred=d, username=username, address=address)
            ).addCallback(lambda _: d)

    @deferred_performer
    def run(_, intent):
        log.msg(format="%(command)s",
                system="SSH[%s@%s]" % (username, address),
                username=username, address=address,
                command=intent.command)
        endpoint = SSHCommandClientEndpoint.existingConnection(
            connection, intent.command)
        return do_remote(endpoint)

    @sync_performer
    def sudo(_, intent):
        return Effect(Run(command='sudo ' + intent.command))

    @sync_performer
    def put(_, intent):
        return Effect(Run(command='echo -n %s > %s'
                                  % (shell_quote(intent.content),
                                     shell_quote(intent.path))))

    @sync_performer
    def comment(_, intent):
        pass

    dispatcher = ComposedDispatcher([
        TypeDispatcher({
            Run: run,
            Sudo: sudo,
            Put: put,
            Comment: comment,
        }),
        base_dispatcher,
    ])

    yield perform(dispatcher, commands)

    yield connection_helper.cleanupConnection(
        connection, False)


@attributes([
    "username", "address", "commands",
])
class X(object):
    pass


@deferred_performer
def perform_ssh(dispatcher, intent):
    return run_with_crochet(
        dispatcher, intent.username, intent.address, intent.commands)
