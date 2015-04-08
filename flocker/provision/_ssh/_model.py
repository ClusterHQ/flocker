from pipes import quote as shell_quote
from pyrsistent import PRecord, field
from effect import Effect


class RunRemotely(PRecord):
    """
    Run some commands on a remote host.

    :ivar bytes address: The address of the remote host to connect to.
    :ivar bytes username: The user to connect as.
    :ivar Effect commands: The commands to run.
    """
    username = field(type=bytes)
    address = field(type=bytes)
    commands = field(type=Effect)


def run_remotely(username, address, commands):
    """
    Run some commands on a remote host.

    :param bytes address: The address of the remote host to connect to.
    :param bytes username: The user to connect as.
    :param Effect commands: The commands to run.

    :return Effect:
    """
    return Effect(RunRemotely(
        username=username, address=address, commands=commands))


class Run(PRecord):
    """
    Run a shell command on a remote host.

    :ivar bytes command: The command to run.
    """
    command = field(type=bytes)

    @classmethod
    def from_args(cls, command_args):
        return cls(command=" ".join(map(shell_quote, command_args)))


class Sudo(PRecord):
    """
    Run a shell command on a remote host with sudo.

    :ivar bytes command: The command to run.
    """
    command = field(type=bytes)

    @classmethod
    def from_args(cls, command_args):
        return cls(command=" ".join(map(shell_quote, command_args)))


class Put(PRecord):
    """
    Create a file with the given content on a remote host.

    :ivar bytes content: The desired contents.
    :ivar bytes path: The remote path to create.
    """
    content = field(type=bytes)
    path = field(type=bytes)


class Comment(PRecord):
    """
    Record a comment to be shown in the documentation corresponding to a task.

    :ivar bytes comment: The desired comment.
    """
    comment = field(type=bytes)


def run(command):
    """
    Run a shell command on a remote host.

    :param bytes command: The command to run.
    """
    return Effect(Run(command=command))


def sudo(command):
    """
    Run a shell command on a remote host with sudo.

    :param bytes command: The command to run.

    :return Effect:
    """
    return Effect(Sudo(command=command))


def put(content, path):
    """
    Create a file with the given content on a remote host.

    :param bytes content: The desired contents.
    :param bytes path: The remote path to create.

    :return Effect:
    """
    return Effect(Put(content=content, path=path))


def comment(comment):
    """
    Record a comment to be shown in the documentation corresponding to a task.

    :param bytes comment: The desired comment.

    :return Effect:
    """
    return Effect(Comment(comment=comment))


def run_from_args(command):
    """
    Run a command on a remote host. This quotes the provided arguments, so they
    are not interpreted by the shell.

    :param list command: The command to run.

    :return Effect:
    """
    return Effect(Run.from_args(command))


def sudo_from_args(command):
    """
    Run a command on a remote host with sudo. This quotes the provided
    arguments, so they are not interpreted by the shell.

    :param list command: The command to run.

    :return Effect:
    """
    return Effect(Sudo.from_args(command))
