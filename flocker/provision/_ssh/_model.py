from collections import MutableSequence
from pipes import quote as shell_quote
from pyrsistent import PRecord, field
from effect import Effect, sync_performer


def identity(arg):
    """Return argument untouched."""
    return arg


class RunRemotely(PRecord):
    """
    Run some commands on a remote host.

    :ivar bytes address: The address of the remote host to connect to.
    :ivar bytes username: The user to connect as.
    :ivar Effect commands: The commands to run.
    :ivar int port: The port of the ssh server to connect to.
    :ivar callable log_command_filter: A filter to apply to any logging
        of the executed command.
    """
    username = field(type=bytes, mandatory=True)
    address = field(type=bytes, mandatory=True)
    commands = field(type=Effect, mandatory=True)
    port = field(type=int, initial=22)
    log_command_filter = field(mandatory=True)


def run_remotely(
        username, address, commands, port=22, log_command_filter=identity):
    """
    Run some commands on a remote host.

    :param bytes address: The address of the remote host to connect to.
    :param bytes username: The user to connect as.
    :param Effect commands: The commands to run.
    :param int port: The port of the ssh server to connect to.
    :param callable log_command_filter: A filter to apply to any logging
        of the executed command.

    :return Effect:
    """
    return Effect(RunRemotely(
        username=username, address=address, commands=commands, port=port,
        log_command_filter=log_command_filter))


def _shell_join(seq):
    """
    Convert a nested list of strings to a shell command.

    Each string in the list is escaped as necessary to allow it to be
    passed to a shell as a single word. If an item is a list, it is a
    nested command, which will be escaped first, and then added as a
    single word to the top-level command.

    For example, ['su', 'root', '-c', ['apt-get', 'update']] becomes
    "su root -c 'apt-get update'".
    """
    result = []
    for word in seq:
        if isinstance(word, (tuple, MutableSequence)):
            word = _shell_join(word)
        escaped = shell_quote(word)
        result.append(escaped)
    return ' '.join(result)


class Run(PRecord):
    """
    Run a shell command on a remote host.

    :ivar bytes command: The command to run.
    :ivar callable log_command_filter: A filter to apply to any logging
        of the executed command.
    """
    command = field(type=bytes, mandatory=True)
    log_command_filter = field(mandatory=True)

    @classmethod
    def from_args(cls, command_args, log_command_filter=identity):
        return cls(
            command=_shell_join(command_args),
            log_command_filter=log_command_filter)


class Sudo(PRecord):
    """
    Run a shell command on a remote host with sudo.

    :ivar bytes command: The command to run.
    :ivar callable log_command_filter: A filter to apply to any logging
        of the executed command.
    """
    command = field(type=bytes, mandatory=True)
    log_command_filter = field(mandatory=True)

    @classmethod
    def from_args(cls, command_args, log_command_filter=identity):
        return cls(
            command=_shell_join(command_args),
            log_command_filter=log_command_filter)


@sync_performer
def perform_sudo(dispatcher, intent):
    """
    Default implementation of `Sudo`.
    """
    return Effect(Run(
        command='sudo ' + intent.command, log_command_filter=identity))


class Put(PRecord):
    """
    Create a file with the given content on a remote host.

    :ivar bytes content: The desired contents.
    :ivar bytes path: The remote path to create.
    :ivar callable log_content_filter: A filter to apply to any logging
        of the transferred content.
    """
    content = field(type=bytes, mandatory=True)
    path = field(type=bytes, mandatory=True)
    log_content_filter = field(mandatory=True)


@sync_performer
def perform_put(dispatcher, intent):
    """
    Default implementation of `Put`.
    """
    def create_put_command(content, path):
        return 'printf -- %s > %s' % (shell_quote(content), shell_quote(path))
    return Effect(Run(
        command=create_put_command(intent.content, intent.path),
        log_command_filter=lambda _: create_put_command(
            intent.log_content_filter(intent.content), intent.path)
        ))


class Comment(PRecord):
    """
    Record a comment to be shown in the documentation corresponding to a task.

    :ivar bytes comment: The desired comment.
    """
    comment = field(type=bytes, mandatory=True)


@sync_performer
def perform_comment(dispatcher, intent):
    """
    Default implementation of `Comment`.
    """


def run(command, log_command_filter=identity):
    """
    Run a shell command on a remote host.

    :param bytes command: The command to run.
    :param callable log_command_filter: A filter to apply to any logging
        of the executed command.
    """
    return Effect(Run(command=command, log_command_filter=log_command_filter))


def sudo(command, log_command_filter=identity):
    """
    Run a shell command on a remote host with sudo.

    :param bytes command: The command to run.
    :param callable log_command_filter: A filter to apply to any logging
        of the executed command.

    :return Effect:
    """
    return Effect(Sudo(command=command, log_command_filter=log_command_filter))


def put(content, path, log_content_filter=identity):
    """
    Create a file with the given content on a remote host.

    :param bytes content: The desired contents.
    :param bytes path: The remote path to create.
    :param callable log_content_filter: A filter to apply to any logging
        of the transferred content.

    :return Effect:
    """
    return Effect(Put(
        content=content, path=path, log_content_filter=log_content_filter))


def comment(comment):
    """
    Record a comment to be shown in the documentation corresponding to a task.

    :param bytes comment: The desired comment.

    :return Effect:
    """
    return Effect(Comment(comment=comment))


def run_from_args(command, log_command_filter=identity):
    """
    Run a command on a remote host. This quotes the provided arguments, so they
    are not interpreted by the shell.

    :param list command: The command to run.
    :param callable log_command_filter: A filter to apply to any logging
        of the executed command.

    :return Effect:
    """
    return Effect(
        Run.from_args(command, log_command_filter=log_command_filter))


def sudo_from_args(command, log_command_filter=identity):
    """
    Run a command on a remote host with sudo. This quotes the provided
    arguments, so they are not interpreted by the shell.

    :param list command: The command to run.
    :param callable log_command_filter: A filter to apply to any logging
        of the executed command.

    :return Effect:
    """
    return Effect(
        Sudo.from_args(command, log_command_filter=log_command_filter))
