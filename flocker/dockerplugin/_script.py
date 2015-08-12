# Copyright ClusterHQ Inc. See LICENSE file for details.

"""
Command to start up the Docker plugin.
"""

from twisted.python.usage import Options
from twisted.internet.endpoints import serverFromString
from twisted.application.internet import StreamServerEndpointService
from twisted.web.server import Site
from twisted.python.filepath import FilePath
from twisted.internet.address import UNIXAddress

from ..common.script import (
    flocker_standard_options, FlockerScriptRunner, main_for_service)
from ._api import VolumePlugin
from ..node.script import get_configuration
from ..apiclient import FlockerClient
from ..control.httpapi import REST_API_PORT

PLUGIN_PATH = FilePath("/run/docker/plugins/flocker/flocker.sock")


@flocker_standard_options
class DockerPluginOptions(Options):
    """
    Command-line options for the Docker plugin.
    """
    optParameters = [
        ["rest-api-port", "p", REST_API_PORT,
         "Port to connect to for control service REST API."],
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
        # Many places in both twisted.web and Klein are unhappy with
        # listening on Unix socket, fix that by pretending we have a port
        # number:
        UNIXAddress.port = 0

        # We can use /etc/flocker/agent.yml and /etc/flocker/node.crt to load
        # some information we need:
        agent_config = get_configuration(options)
        control_host = agent_config['control-service']['hostname']
        node_id = agent_config['node-credential'].uuid

        certificates_path = options["agent-config"].parent()
        control_port = options["rest-api-port"]
        flocker_client = FlockerClient(reactor, control_host, control_port,
                                       certificates_path.child(b"cluster.crt"),
                                       certificates_path.child(b"api.crt"),
                                       certificates_path.child(b"api.key"))

        parent = PLUGIN_PATH.parent()
        if not parent.exists():
            parent.makedirs()
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
