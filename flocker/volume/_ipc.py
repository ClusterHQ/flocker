# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""Inter-process communication for the volume manager.

Specific volume managers ("nodes") may wish to push data to other
nodes. In the current iteration this is done over SSH, using a blocking
API. In some future iteration this will be replaced with an actual
well-specified communication protocol between daemon processes using
Twisted's event loop.
"""

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


@attributes(["host", "port", "private_key"])
@implementer(INode)
class SSHNode(object):
    """A remote node that can be SSHed into.

    :ivar bytes host: The hostname or IP.
    :ivar int port: The port number of the SSH server.
    :ivar FilePath private_key: Path to private key to use when talking to
        SSH server.
    """


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
