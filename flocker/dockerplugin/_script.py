# Copyright ClusterHQ Inc. See LICENSE file for details.

"""
Command to start up the Docker plugin.
"""

from twisted.python.usage import Options
from twisted.internet.endpoints import serverFromString
from twisted.application.internet import StreamServerEndpointService
from twisted.web.server import Site
from twisted.python.filepath import FilePath

from ..common.script import (
    flocker_standard_options, FlockerScriptRunner, main_for_service)
from ._api import VolumePlugin
from ..node.script import get_configuration
from ..apiclient import FlockerClient

PLUGIN_PATH = FilePath("/run/docker/plugins/flocker/flocker.sock")


@flocker_standard_options
class DockerPluginOptions(Options):
    """
    Command-line options for the Docker plugin.
    """
    optParameters = [
        ["agent-config", "c", "/etc/flocker/agent.yml",
         "The configuration file for the local agent."],
    ]

    def postOptions(self):
        self['agent-config'] = FilePath(self['agent-config'])


class DockerPluginScript(object):
    """
    Start the Docker plugin.
    """
    def main(self, reactor, options):
        # We can use /etc/flocker/agent.yml and /etc/flocker/node.crt to load
        # some information we need:
        agent_config = get_configuration(options)
        control_host = agent_config['control-service']['hostname']
        control_port = agent_config['control-service']['port']
        node_id = agent_config['node-credential'].uuid

        certificates_path = options["agent-config"].parent()
        flocker_client = FlockerClient(reactor, control_host, control_port,
                                       certificates_path.child(b"cluster.crt"),
                                       certificates_path.child(b"api.crt"),
                                       certificates_path.child(b"api.key"))

        PLUGIN_PATH.parent().makedirs()
        endpoint = serverFromString(
            reactor, "unix:{}:mode=600".format(PLUGIN_PATH.path))
        service = StreamServerEndpointService(endpoint, Site(
            VolumePlugin(reactor, flocker_client, node_id).app.resource()))
        return main_for_service(reactor, service)


def docker_plugin_main():
    """
    Script entry point that runs the Docker plugin.
    """
    return FlockerScriptRunner(script=DockerPluginScript(),
                               options=DockerPluginOptions()).main()
