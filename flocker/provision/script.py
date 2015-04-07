# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
The command-line ``flocker-provision`` tool.
"""
import yaml
from twisted.internet.defer import succeed, fail
from twisted.python.usage import Options

from zope.interface import implementer
# TODO separate FEEDBACK_CLI_TEXT to somewhere shared from flocker.cli.script
from flocker.cli.script import FEEDBACK_CLI_TEXT

from ..common.script import (flocker_standard_options, ICommandLineScript,
                             FlockerScriptRunner)

from flocker.provision import CLOUD_PROVIDERS, PackageSource
from flocker.provision._install import (
    configure_cluster,
)


class CreateOptions(Options):
    # TODO longdesc and synopsis
    # TODO look at docker machine for inspiration
    optParameters = [
        ['driver', 'd', 'rackspace', 'choose cloud provider'],
        ['rackspace-username', None, None, 'Rackspace account username'],
        ['rackspace-api-key', None, None, 'Rackspace API key'],
        ['rackspace-region', None, None, 'Rackspace region'],
        ['rackspace-ssh-key-name', None, None, 'Name of Rackspace SSH key.'],
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


def create(reactor, options):
    # Only rackspace for the moment
    provisioner = CLOUD_PROVIDERS[options['driver']](
        username=options['rackspace-username'],
        key=options['rackspace-api-key'],
        region=options['rackspace-region'],
        keyname=options['rackspace-ssh-key-name'],
    )

    nodes = []
    for index in range(options['num-agent-nodes'] + 1):
        name = "flocker-provisioning-script-%d" % (index,)
        try:
            print "Creating node %d: %s" % (index, name)
            node = provisioner.create_node(
                name=name,
                distribution='centos-7',
            )
        except:
            print "Error creating node %d: %s" % (index, name)
            print "It may have leaked into the cloud."
            raise

        nodes.append(node)

        node.provision(package_source=PackageSource(),
                       variants=set())
        del node

    control_node = nodes[0].address
    agent_nodes = [node.address for node in nodes[1:]]
    configure_cluster(control_node=control_node, agent_nodes=agent_nodes)
    print yaml.safe_dump({
        'control_node': control_node,
        'agent_nodes': agent_nodes,
    })
    return succeed(None)


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
        if options.subCommand == 'create':
            return create(reactor, options.subOptions)
        else:
            return fail(ValueError("Unknown subCommand."))


def flocker_provision_main():
    # There is nothing to log at the moment, so logging is disabled.
    return FlockerScriptRunner(
        script=ProvisionScript(),
        options=ProvisionOptions(),
        logging=False,
    ).main()
