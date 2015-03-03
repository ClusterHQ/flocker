# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Utilities for executing commands on a remote host via SSH.
"""

from characteristic import attributes
from pipes import quote as shell_quote


@attributes(["comment"])
class Comment(object):
    """
    Record a comment to be shown in the documentation corresponding to a task.

    :param bytes comment: The desired comment.
    """


@attributes(["command"])
class Run(object):
    """
    Run a shell command on a remote host.

    :param bytes command: The command to run.
    """
    @classmethod
    def from_args(cls, command_args):
        return cls(command=" ".join(map(shell_quote, command_args)))


@attributes(["command"])
class Sudo(object):
    """
    Run a shell command on a remote host.

    :param bytes command: The command to run.
    """
    @classmethod
    def from_args(cls, command_args):
        return cls(command=" ".join(map(shell_quote, command_args)))


@attributes(["content", "path"])
class Put(object):
    """
    Create a file with the given content on a remote host.

    :param bytes content: The desired contests.
    :param bytes path: The remote path to create.
    """


def run_with_fabric(username, address, commands):
    """
    Run a series of commands on a remote host.

    :param bytes username: User to connect as.
    :param bytes address: Address to connect to
    :param list commands: List of commands to run.
    """
    from fabric.api import settings, run, put, sudo
    from fabric.network import disconnect_all
    from StringIO import StringIO

    handlers = {
        Run: lambda e: run(e.command),
        Sudo: lambda e: sudo(e.command),
        Put: lambda e: put(StringIO(e.content), e.path),
        Comment: lambda e: None,
    }

    host_string = "%s@%s" % (username, address)
    with settings(
            connection_attempts=24,
            timeout=5,
            pty=False,
            host_string=host_string):

        for command in commands:
            handlers[type(command)](command)
    disconnect_all()
