from pipes import quote as shell_quote
from pyrsistent import PRecord, field
from effect import Effect


class RunRemotely(PRecord):
    username = field(type=bytes)
    address = field(type=bytes)
    commands = field()


class Run(PRecord):
    """
    Run a shell command on a remote host.

    :param bytes command: The command to run.
    """
    command = field(type=bytes)

    @classmethod
    def from_args(cls, command_args):
        return cls(command=" ".join(map(shell_quote, command_args)))


class Sudo(PRecord):
    """
    Run a shell command on a remote host.

    :param bytes command: The command to run.
    """
    command = field(type=bytes)

    @classmethod
    def from_args(cls, command_args):
        return cls(command=" ".join(map(shell_quote, command_args)))


class Put(PRecord):
    """
    Create a file with the given content on a remote host.

    :param bytes content: The desired contests.
    :param bytes path: The remote path to create.
    """
    content = field(type=bytes)
    path = field(type=bytes)


class Comment(PRecord):
    """
    Record a comment to be shown in the documentation corresponding to a task.

    :param bytes comment: The desired comment.
    """
    comment = field(type=bytes)


def run(command):
    return Effect(Run(command=command))


def sudo(command):
    return Effect(Sudo(command=command))


def put(content, path):
    return Effect(Put(content=content, path=path))


def comment(comment):
    return Effect(Comment(comment=comment))


def run_from_args(command):
    return Effect(Run.from_args(command))


def sudo_from_args(command):
    return Effect(Sudo.from_args(command))
