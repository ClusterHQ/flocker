# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""The command-line ``flocker-node`` tool."""

import sys

from twisted.python.usage import Options
from twisted.python.filepath import FilePath
from twisted.internet.defer import succeed

from zope.interface import implementer

from ..common.script import (
    flocker_standard_options, FlockerScriptRunner, ICommandLineScript)


__all__ = [
    # TODO
]


@flocker_standard_options
class NodeOptions(Options):
    """Command line options for ``flocker-volume`` volume management tool."""

    longdesc = """flocker-volume allows you to manage volumes, filesystems
    that can be attached to Docker containers.

    """
    synopsis = "Usage: flocker-node [OPTIONS]"

    optParameters = []

    subCommands = []

    def parseArgs(self, deployment_config, app_config):
        self['deployment_config'] = deployment_config
        self['app_config'] = app_config


@implementer(ICommandLineScript)
class NodeScript(object):
    """A volume manager script.

    :ivar IService _service: ``VolumeService`` by default but can be overridden
        for testing purposes.
    """

    def main(self, reactor, options):
        """Run a volume management server

        The server will be configured according to the supplied options.

        See :py:meth:`ICommandLineScript.main` for parameter documentation.
        """
        return succeed(None)


def flocker_node_main():
    return FlockerScriptRunner(
        script=NodeScript(),
        options=NodeOptions()
    ).main()
