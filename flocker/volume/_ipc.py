# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""Inter-process communication for the volume manager.

Specific volume managers ("nodes") may wish to push data to other
nodes. In the current iteration this is done over SSH, using a blocking
API. In some future iteration this will be replaced with an actual
well-specified communication protocol between daemon processes using
Twisted's event loop (https://github.com/ClusterHQ/flocker/issues/154).
"""

import subprocess
from contextlib import contextmanager
from io import BytesIO

from zope.interface import Interface, implementer

from characteristic import attributes


class INode(Interface):
    """A remote node with which this node can communicate."""

    def run(remote_command):
        """Context manager that runs a remote command and return its stdin.

        The returned file-like object will be closed by this object.

        :param remote_command: ``list`` of ``bytes``, the command to run
            remotely along with its arguments.

        :return: file-like object that can be written to.
        """


@attributes(["initial_command_arguments"])
@implementer(INode)
class ProcessNode(object):
    """Communicate with a remote node using a subprocess.

    :param initial_command_arguments: ``list`` of ``bytes``, initial
        command arguments to prefix to whatever arguments get passed to
        ``run()``.
    """
    @contextmanager
    def run(self, remote_command):
        process = subprocess.Popen(
            self.initial_command_arguments + remote_command,
            stdin=subprocess.PIPE)
        try:
            yield process.stdin
        finally:
            process.stdin.close()
            exit_code = process.wait()
            if exit_code:
                raise IOError("Bad exit")

    @classmethod
    def using_ssh(cls, host, port, username, private_key):
        """Create a ``ProcessNode`` that communicate over SSH.

        :param bytes host: The hostname or IP.
        :param int port: The port number of the SSH server.
        :param bytes username: The username to SSH as.
        :param FilePath private_key: Path to private key to use when talking to
            SSH server.

        :return: ``ProcessNode`` instance that communicates over SSH.
        """
        return cls(initial_command_arguments=[
            b"ssh",
            b"-q", # suppress warnings
            b"-i", private_key.path,
            b"-l", username,
            b"-o", b"StrictHostKeyChecking=no", # we're ok with unknown hosts
            b"-p", b"%d" % (port,), host])


@implementer(INode)
class FakeNode(object):
    """Pretend to run a command.

    This is useful for testing.

    :ivar remote_command: The arguments to the last call to ``run()``.
    :ivar stdin: `BytesIO` returned from last call to ``run()``.
    """
    @contextmanager
    def run(self, remote_command):
        """Store arguments and in-memory "stdin"."""
        self.stdin = BytesIO()
        self.remote_command = remote_command
        yield self.stdin
        self.stdin.seek(0, 0)
