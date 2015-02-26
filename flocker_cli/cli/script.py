# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
The command-line ``flocker`` CLI tool.
"""

from twisted.internet.defer import succeed
from twisted.python.usage import Options

from zope.interface import implementer

from .common import (flocker_standard_options, ICommandLineScript,
                     FlockerScriptRunner)


@flocker_standard_options
class CLIOptions(Options):
    """
    Command line options for ``flocker`` CLI.

    """
    longdesc = """flocker does nothing (yet).

    """

    synopsis = ("Usage: flocker [OPTIONS] "
                "\n"
                "If you have any issues or feedback, you can talk to us: "
                "http://docs.clusterhq.com/en/latest/gettinginvolved/"
                "contributing.html#talk-to-us")


@implementer(ICommandLineScript)
class CLIScript(object):
    """
    A script to start configured deployments on a Flocker cluster.
    """
    def main(self, reactor, options):
        """
        See :py:meth:`ICommandLineScript.main` for parameter documentation.

        :return: A ``Deferred`` which fires when the deployment is complete or
                 has encountered an error.
        """
        return succeed(None)


def flocker_cli_main():
    return FlockerScriptRunner(
        script=CLIScript(),
        options=CLIOptions(),
        logging=False,
    ).main()
