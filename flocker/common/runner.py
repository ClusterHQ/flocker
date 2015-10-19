# -*- test-case-name: admin.test.test_runner -*-
# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
# -*- test-case-name: flocker.common.test.test_runner -*-
"""
Tools for running commands.
"""
import os
from pipes import quote as shell_quote

from characteristic import attributes
from eliot import MessageType, ActionType, Field
from eliot.twisted import DeferredContext

from twisted.python.failure import Failure
from twisted.internet.error import ProcessTerminated, ProcessDone
from twisted.internet.defer import Deferred
from twisted.internet.protocol import ProcessProtocol

from twisted.protocols.basic import LineOnlyReceiver


RUN_ACTION = ActionType(
    action_type="flocker.common.runner:run",
    startFields=[
        Field.for_types(u"command", [list], u"The command.")
    ],
    successFields=[],
    description="Run a command.",
)
RUN_OUTPUT_MESSAGE = MessageType(
    message_type="flocker.common.runner:run:stdout",
    fields=[
        Field.for_types(u"line", [bytes], u"The output."),
    ],
    description=u"A line of command output.",
)
RUN_ERROR_MESSAGE = MessageType(
    message_type="flocker.common.runner:run:stderr",
    fields=[
        Field.for_types(u"line", [bytes], u"The error."),
    ],
    description=u"A line of command stderr.",
)


class RemoteFileNotFound(Exception):
    """
    A file on a remote server was not found.
    """
    def __init__(self, remote_path):
        """
        :param bytes remote_path: A ``username@host:path``-style string
            describing the file that was not found.
        """
        Exception.__init__(self, remote_path)
        self.remote_path = remote_path

    def __str__(self):
        return repr(self)


# LineOnlyReceiver is mutable, so can't use pyrsistent
@attributes([
    "handle_line",
])
class _LineParser(LineOnlyReceiver, object):
    """
    Parser that breaks input into lines, and writes it to ouput.

    :ivar handle_line: Callable to call with parsed lines.
    """
    delimiter = b'\n'

    def __init__(self):
        self.transport = type('', (object,), {})()
        self.transport.disconnecting = False

    def lineReceived(self, line):
        self.handle_line(line)


@attributes([
    "deferred",
    "handle_stdout",
    "handle_stderr",
])
class CommandProtocol(ProcessProtocol, object):
    """
    Protocol that logs the lines of a remote command.

    :ivar Deferred deferred: Deferred to fire when the command finishes
        If the command finished successfully, will fire with ``None``.
        Otherwise, errbacks with the reason.
    :ivar handle_stdout: Callable to call with lines from stdout.
    :ivar handle_stderr: Callable to call with lines from stderr.
    """
    def __init__(self):
        self._stdout_parser = _LineParser(handle_line=self.handle_stdout)
        self._stderr_parser = _LineParser(handle_line=self.handle_stderr)

    def outReceived(self, data):
        self._stdout_parser.dataReceived(data)

    def errReceived(self, data):
        self._stderr_parser.dataReceived(data)

    def processEnded(self, reason):
        if reason.check(ProcessDone):
            self.deferred.callback(None)
        else:
            self.deferred.errback(reason)


def run(reactor, command, handle_stdout=None, handle_stderr=None, **kwargs):
    """
    Run a process and kill it if the reactor stops.

    :param reactor: Reactor to use.
    :param list command: The command to run.
    :param handle_stdout: Callable that will be called with lines parsed
        from the command stdout. By default logs an Eliot message.
    :param handle_stderr: Callable that will be called with lines parsed
        from the command stderr. By default logs an Eliot message.
    :return Deferred: Deferred that fires when the process is ended.
    """
    if 'env' not in kwargs:
        kwargs['env'] = os.environ

    action = RUN_ACTION(command=command)

    if handle_stdout is None:
        def handle_stdout(line):
            RUN_OUTPUT_MESSAGE(
                line=line,
            ).write(action=action)

    if handle_stderr is None:
        def handle_stderr(line):
            RUN_ERROR_MESSAGE(
                line=line,
            ).write(action=action)

    protocol_done = Deferred()
    protocol = CommandProtocol(
        deferred=protocol_done,
        handle_stdout=handle_stdout,
        handle_stderr=handle_stderr,
    )

    with action.context():
        protocol_done = DeferredContext(protocol_done)
        reactor.spawnProcess(protocol, command[0], command, **kwargs)

        def unregister_killer(result, trigger_id):
            try:
                reactor.removeSystemEventTrigger(trigger_id)
            except:
                # If we can't remove the trigger, presumably it has already
                # been removed (or run). In any case, there is nothing sensible
                # to do if this fails.
                pass
            return result
        trigger_id = reactor.addSystemEventTrigger(
            'before', 'shutdown', protocol.transport.signalProcess, 'TERM')
        protocol_done.addBoth(unregister_killer, trigger_id)

        return protocol_done.addActionFinish()

SSH_OPTIONS = [
    b"-C",  # compress traffic
    b"-q",  # suppress warnings
    # We're ok with unknown hosts.
    b"-o", b"StrictHostKeyChecking=no",
    # The tests hang if ControlMaster is set, since OpenSSH won't
    # ever close the connection to the test server.
    b"-o", b"ControlMaster=no",
    # Some systems (notably Ubuntu) enable GSSAPI authentication which
    # involves a slow DNS operation before failing and moving on to a
    # working mechanism.  The expectation is that key-based auth will
    # be in use so just jump straight to that.
    b"-o", b"PreferredAuthentications=publickey"
]


def run_ssh(reactor, username, host, command, **kwargs):
    """
    Run a process on a remote server using the locally installed ``ssh``
    command and kill it if the reactor stops.

    :param reactor: Reactor to use.
    :param username: The username to use when logging into the remote server.
    :param host: The hostname or IP address of the remote server.
    :param list command: The command to run remotely.
    :param dict kwargs: Remaining keyword arguments to pass to ``run``.
    :return Deferred: Deferred that fires when the process is ended.
    """
    ssh_command = [
        b"ssh",
    ] + SSH_OPTIONS + [
        b"-l", username,
        host,
        ' '.join(map(shell_quote, command)),
    ]

    return run(
        reactor,
        ssh_command,
        **kwargs
    )


def download_file(reactor, username, host, remote_path, local_path):
    """
    Run the local ``scp`` command to download a single file from a remote host
    and kill it if the reactor stops.

    :param reactor: Reactor to use.
    :param username: The username to use when logging into the remote server.
    :param host: The hostname or IP address of the remote server.
    :param FilePath remote_path: The path of the file on the remote host.
    :param FilePath local_path: The path of the file on the local host.

    :return Deferred: Deferred that fires when the process is ended.  If the
        file isn't found on the remote server, it fires with ``FileNotFound``.
    """
    remote_path = username + b'@' + host + b':' + remote_path.path
    scp_command = [
        b"scp",
    ] + SSH_OPTIONS + [
        remote_path,
        local_path.path
    ]

    # A place to hold failure state between parsing stderr and needing to fire
    # a Deferred.
    failed_reason = []

    def check_for_missing(line):
        """
        Notice scp's particular way of describing the file-not-found condition
        and turn it into a more easily recognized form.
        """
        if b"No such file or directory" in line:
            failed_reason.append(RemoteFileNotFound(remote_path))

    scp_result = run(
        reactor,
        scp_command,
        handle_stderr=check_for_missing,
    )

    def scp_failed(reason):
        """
        Check for a known error with the scp attempt and turn the normal
        failure into a more meaningful one.
        """
        reason.trap(ProcessTerminated)
        if failed_reason:
            return Failure(failed_reason[0])

    scp_result.addErrback(scp_failed)
    return scp_result
