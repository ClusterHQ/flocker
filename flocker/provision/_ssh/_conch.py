from pipes import quote as shell_quote
from twisted.python import log

from characteristic import attributes

from effect import (
    sync_performer, TypeDispatcher, ComposedDispatcher, Effect,
    )
from effect.twisted import (
    make_twisted_dispatcher,
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

from flocker.testtools import loop_until

from ._model import Run, Sudo, Put, Comment, RunRemotely

from .._effect import dispatcher as base_dispatcher


@attributes([
    "deferred",
    "address",
    "username",
])
class CommandProtocol(LineOnlyReceiver, object):
    """
    Protocol that logs the lines of a remote command.

    :ivar Deferred deferred: Deferred to fire when the command finishes
        If the command finished succesfuly, will fire with ``None``.
        Otherwise, errbacks with the reason.
    :ivar bytes username: For logging.
    :ivar bytes address: For logging.
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
        log.msg(format="%(line)s",
                system="SSH[%s@%s]" % (self.username, self.address),
                username=self.username, address=self.address, line=line)


@sync_performer
def perform_sudo(dispatcher, intent):
    """
    See :py:class:`Sudo`.
    """
    return Effect(Run(command='sudo ' + intent.command))


@sync_performer
def perform_put(dispatcher, intent):
    """
    See :py:class:`Put`.
    """
    return Effect(Run(command='echo -n %s > %s'
                              % (shell_quote(intent.content),
                                 shell_quote(intent.path))))


@sync_performer
def perform_comment(dispatcher, intent):
    """
    See :py:class:`Comment`.
    """


def get_ssh_dispatcher(connection, username, address):
    """
    :ivar bytes username: For logging.
    :ivar bytes address: For logging.
    :ivar connection: The SSH connection run commands on.
    """

    @deferred_performer
    def perform_run(dispatcher, intent):
        log.msg(format="%(command)s",
                system="SSH[%s@%s]" % (username, address),
                username=username, address=address,
                command=intent.command)
        endpoint = SSHCommandClientEndpoint.existingConnection(
            connection, intent.command)
        d = Deferred()
        connectProtocol(endpoint, CommandProtocol(
            deferred=d, username=username, address=address))
        return d

    return TypeDispatcher({
        Run: perform_run,
        Sudo: perform_sudo,
        Put: perform_put,
        Comment: perform_comment,
    })


def get_connection_helper(address, username, port):
    """
    Get a :class:`twisted.conch.endpoints._ISSHConnectionCreator` to connect to
    the given remote.

    :param bytes address: The address of the remote host to connect to.
    :param bytes username: The user to connect as.
    :param int port: The port of the ssh server to connect to.

    :return _ISSHConnectionCreator:
    """
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

    return _NewConnectionHelper(
        reactor, address, port, None, username,
        keys=keys,
        password=None,
        agentEndpoint=agentEndpoint,
        knownHosts=None, ui=ConsoleUI(lambda: _ReadFile(b"yes")))


@deferred_performer
@inlineCallbacks
def perform_run_remotely(base_dispatcher, intent):
    connection_helper = get_connection_helper(
        username=intent.username, address=intent.address, port=intent.port)

    def connect():
        connection = connection_helper.secureConnection()
        connection.addErrback(lambda _: False)
        return connection

    connection = yield loop_until(connect)

    dispatcher = ComposedDispatcher([
        get_ssh_dispatcher(
            connection=connection,
            username=intent.username, address=intent.address,
        ),
        base_dispatcher,
    ])

    yield perform(dispatcher, intent.commands)

    yield connection_helper.cleanupConnection(
        connection, False)


def make_dispatcher(reactor):
    return ComposedDispatcher([
        TypeDispatcher({
            RunRemotely: perform_run_remotely,
        }),
        make_twisted_dispatcher(reactor),
        base_dispatcher,
    ])
