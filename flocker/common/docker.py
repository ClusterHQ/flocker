# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""Docker Client"""

import os
import json

from twisted.internet.endpoints import ProcessEndpoint, connectProtocol

from characteristic import attributes

from .process import _AccumulatingProtocol, CommandFailed


@attributes(['container_name'])
class UnknownContainer(Exception):
    """
    The named container does not exist.
    """

class DockerClient(object):
    """
    An API for interacting with Docker.

    Communication with Docker should be done via its API, not with this
    approach, but that depends on unreleased Twisted 14.1:
    https://github.com/hybridlogic/flocker/issues/64
    """
    def __init__(self, reactor=None):
        if reactor is None:
            from twisted.internet import reactor
        self._reactor = reactor

    def command(self, arguments):
        """Run the ``docker`` command-line tool with the given arguments.

        :param arguments: A ``list`` of ``bytes``, command-line arguments to
        ``docker``.

        :return: A :class:`Deferred` firing with the bytes of the result (on
            exit code 0), or errbacking with :class:`CommandFailed` or
            :class:`BadArguments` depending on the exit code (1 or 2).
        """
        endpoint = ProcessEndpoint(self._reactor, b"docker", [b"docker"] + arguments,
                                   os.environ)
        d = connectProtocol(endpoint, _AccumulatingProtocol())
        d.addCallback(lambda protocol: protocol._result)
        return d

    def inspect(self, container_name):
        """
        """
        d = self.command(['inspect', container_name])
        d.addCallback(json.loads)
        def handle_command_failed(failure):
            failure.trap(CommandFailed)
            raise UnknownContainer(container_name=container_name)
        d.addErrback(handle_command_failed)
        return d

    def remove(self, container_name, force=False):
        args = [b'rm']
        if force:
            args.append(b'--force')
        args.append(container_name)
        return self.command(args)
