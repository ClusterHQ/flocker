# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
The command-line ``flocker-provision`` tool.
"""
from twisted.internet.defer import succeed
from twisted.python.usage import Options

from zope.interface import implementer
# TODO separate FEEDBACK_CLI_TEXT to somewhere shared from flocker.cli.script
from flocker.cli.script import FEEDBACK_CLI_TEXT

from ..common.script import (flocker_standard_options, ICommandLineScript,
                             FlockerScriptRunner)


class CreateOptions(Options):
    # TODO longdesc and synopsis
    # TODO look at docker machine for inspiration
    optParameters = [
        ['driver', 'd', 'rackspace', 'choose cloud provider'],
        ['rackspace-username', None, None, 'Rackspace account username'],
        ['rackspace-api-key', None, None, 'Rackspace API key'],
        ['rackspace-region', None, None, 'Rackspace region'],
        ['num-agent-nodes', 'n', 3, 'how many nodes to create'],
    ]

@flocker_standard_options
class ProvisionOptions(Options):
    """
    Command line options for ``flocker-provision``.
    """
    longdesc = """flocker-provision...

    """

    # TODO this is from flocker-provision
    synopsis = ("Usage: flocker-provision [OPTIONS] "
                "DEPLOYMENT_CONFIGURATION_PATH APPLICATION_CONFIGURATION_PATH"
                "{feedback}").format(feedback=FEEDBACK_CLI_TEXT)

    # TODO check other commands for period
    subCommands = [['create', None, CreateOptions, "Create a Flocker cluster"]]

    def parseArgs(self):
        pass


@implementer(ICommandLineScript)
class ProvisionScript(object):
    """
    A command-line script to interact with a cluster via the API.
    """
    def main(self, reactor, options):
        """
        See :py:meth:`ICommandLineScript.main` for parameter documentation.

        :return: A ``Deferred`` which fires when the deployment is complete or
                 has encountered an error.
        """
        return succeed(None)


def flocker_provision_main():
    # There is nothing to log at the moment, so logging is disabled.
    return FlockerScriptRunner(
        script=ProvisionScript(),
        options=ProvisionOptions(),
        logging=False,
    ).main()
