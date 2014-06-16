# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""Inter-process communication for the volume manager.

Specific volume managers ("nodes") may wish to push data to other
nodes. In the current iteration this is done over SSH. In some future
iteration this will be replaced with an actual well-specified
communication protocol between daemon processes.
"""

from zope.interface import Interface, implementer

from characteristic import attributes


class INode(Interface):
    """A remote node with which this node can communicate."""

    def run(remote_command):
        """Run a remote command and return its stdin.

        :param remote_command: ``list`` of ``bytes``, the command to run
            remotely along with its arguments.

        :return: file-like object that can be written to.
        """


@attributes(["host", "port", "private_key"], defaults={"port": 22})
@implementer(INode)
class SSHNode(object):
    """A remote node that can be SSHed into.

    :ivar bytes host: The hostname or IP.
    :ivar int port: The port number of the SSH server.
    :ivar FilePath private_key: Path to private key to use when talking to
        SSH server.
    """


@implementer(INode)
class LocalNode(object):
    """Run all processes on the local machine.

    This is useful for testing.
    """
