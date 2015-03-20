from pipes import quote as shell_quote
from pyrsistent import PRecord, field
from twisted.python import log

from effect import (
    sync_performer, TypeDispatcher, ComposedDispatcher, Effect)
from effect.twisted import (
    perform, deferred_performer, make_twisted_dispatcher)
from twisted.conch.endpoints import (
    SSHCommandClientEndpoint, _NewConnectionHelper, _ReadFile, ConsoleUI)

from crochet import run_in_reactor
from crochet import setup
from twisted.conch.ssh.keys import Key
from twisted.internet import reactor
from twisted.internet.defer import Deferred
from twisted.internet.endpoints import UNIXClientEndpoint, connectProtocol
from twisted.internet.error import ConnectionDone
from twisted.protocols.basic import LineOnlyReceiver
from twisted.python.filepath import FilePath
import os


class CommandProtocol(LineOnlyReceiver, PRecord, object):
    delimiter = b'\n'

    deferred = field(type=Deferred)
    address = field(type=bytes)
    username = field(type=bytes)

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


def run_with_crochet(username, address, commands):
    from ._install import Run, Sudo, Put, Comment
    setup()
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
    connection = run_in_reactor(connection_helper.secureConnection)().wait()

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
        make_twisted_dispatcher(reactor),
    ])

    run_in_reactor(perform)(dispatcher, commands).wait()

    run_in_reactor(connection_helper.cleanupConnection)(
        connection, False).wait()
