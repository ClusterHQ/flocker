from pipes import quote as shell_quote

from characteristic import attributes

from eliot import Message, MessageType, Field

from effect import (
    sync_performer, TypeDispatcher, ComposedDispatcher, Effect,
    )
from effect.twisted import (
    make_twisted_dispatcher,
)
from effect.twisted import (
    perform, deferred_performer)

from twisted.conch.endpoints import (
    SSHCommandClientEndpoint,
    # https://twistedmatrix.com/trac/ticket/7861
    _NewConnectionHelper,
    # https://twistedmatrix.com/trac/ticket/7862
    _ReadFile, ConsoleUI,
)

from twisted.conch.client.knownhosts import KnownHostsFile
from twisted.internet import reactor
from twisted.internet.defer import Deferred, inlineCallbacks
from twisted.internet.endpoints import UNIXClientEndpoint, connectProtocol
from twisted.internet.error import ConnectionDone
from twisted.protocols.basic import LineOnlyReceiver
from twisted.python.filepath import FilePath
import os

from flocker.testtools import loop_until

from ._model import Run, Sudo, Put, Comment, RunRemotely, identity

from .._effect import dispatcher as base_dispatcher

from ._monkeypatch import patch_twisted_7672

RUN_OUTPUT_MESSAGE = MessageType(
    message_type="flocker.provision.ssh:run:output",
    fields=[
        Field.for_types(u"line", [bytes], u"The output."),
    ],
    description=u"A line of command output.",
)


def extReceived(self, type, data):
    from twisted.conch.ssh.connection import EXTENDED_DATA_STDERR
    if type == EXTENDED_DATA_STDERR:
        self.dataReceived(data)


@attributes([
    "deferred",
    "context",
])
class CommandProtocol(LineOnlyReceiver, object):
    """
    Protocol that logs the lines of a remote command.

    :ivar Deferred deferred: Deferred to fire when the command finishes
        If the command finished successfully, will fire with ``None``.
        Otherwise, errbacks with the reason.
    :ivar Message context: The eliot message context to log.
    """
    delimiter = b'\n'

    def connectionMade(self):
        from functools import partial
        self.transport.disconnecting = False
        # SSHCommandClientEndpoint doesn't support capturing stderr.
        # We patch the SSHChannel to interleave it.
        # https://twistedmatrix.com/trac/ticket/7893
        self.transport.extReceived = partial(extReceived, self)

    def connectionLost(self, reason):
        if reason.check(ConnectionDone):
            self.deferred.callback(None)
        else:
            self.deferred.errback(reason)

    def lineReceived(self, line):
        self.context.bind(
            message_type="flocker.provision.ssh:run:output",
            line=line,
        ).write()


@sync_performer
def perform_sudo(dispatcher, intent):
    """
    See :py:class:`Sudo`.
    """
    return Effect(Run(
        command='sudo ' + intent.command, log_command_filter=identity))


@sync_performer
def perform_put(dispatcher, intent):
    """
    See :py:class:`Put`.
    """
    def create_put_command(content, path):
        return 'printf -- %s > %s' % (shell_quote(content), shell_quote(path))
    return Effect(Run(
        command=create_put_command(intent.content, intent.path),
        log_command_filter=lambda _: create_put_command(
            intent.log_content_filter(intent.content), intent.path)
        ))


@sync_performer
def perform_comment(dispatcher, intent):
    """
    See :py:class:`Comment`.
    """


def get_ssh_dispatcher(connection, context):
    """
    :param Message context: The eliot message context to log.
    :param connection: The SSH connection run commands on.
    """

    @deferred_performer
    def perform_run(dispatcher, intent):
        context.bind(
            message_type="flocker.provision.ssh:run",
            command=intent.log_command_filter(intent.command),
        ).write()
        endpoint = SSHCommandClientEndpoint.existingConnection(
            connection, intent.command)
        d = Deferred()
        connectProtocol(endpoint, CommandProtocol(
            deferred=d, context=context))
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
    try:
        agentEndpoint = UNIXClientEndpoint(
            reactor, os.environ["SSH_AUTH_SOCK"])
    except KeyError:
        agentEndpoint = None

    return _NewConnectionHelper(
        reactor, address, port, None, username,
        keys=None,
        password=None,
        agentEndpoint=agentEndpoint,
        knownHosts=KnownHostsFile.fromPath(FilePath("/dev/null")),
        ui=ConsoleUI(lambda: _ReadFile(b"yes")))


@deferred_performer
@inlineCallbacks
def perform_run_remotely(base_dispatcher, intent):
    connection_helper = get_connection_helper(
        username=intent.username, address=intent.address, port=intent.port)

    context = Message.new(
        username=intent.username, address=intent.address, port=intent.port)

    def connect():
        connection = connection_helper.secureConnection()
        connection.addErrback(lambda _: False)
        return connection

    connection = yield loop_until(connect)

    dispatcher = ComposedDispatcher([
        get_ssh_dispatcher(
            connection=connection,
            context=context,
        ),
        base_dispatcher,
    ])

    yield perform(dispatcher, intent.commands)

    yield connection_helper.cleanupConnection(
        connection, False)


def make_dispatcher(reactor):
    patch_twisted_7672()
    return ComposedDispatcher([
        TypeDispatcher({
            RunRemotely: perform_run_remotely,
        }),
        make_twisted_dispatcher(reactor),
        base_dispatcher,
    ])
