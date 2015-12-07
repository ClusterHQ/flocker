# Copyright ClusterHQ Inc. See LICENSE file for details.

"""
Command to start up the Docker plugin.
"""

from os import umask
from stat import S_IRUSR, S_IWUSR, S_IXUSR

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
    def _create_listening_directory(self, directory_path):
        """
        Create the parent directory for the Unix socket if it doesn't exist.

        :param FilePath directory_path: The directory to create.
        """
        original_umask = umask(0)
        try:
            if not directory_path.exists():
                directory_path.makedirs()
            directory_path.chmod(S_IRUSR | S_IWUSR | S_IXUSR)
        finally:
            umask(original_umask)

    def main(self, reactor, options):
        # We can use /etc/flocker/agent.yml and /etc/flocker/node.crt to load
        # some information we need:
        agent_config = get_configuration(options)
        control_host = agent_config['control-service']['hostname']

        certificates_path = options["agent-config"].parent()
        control_port = options["rest-api-port"]
        flocker_client = FlockerClient(reactor, control_host, control_port,
                                       certificates_path.child(b"cluster.crt"),
                                       certificates_path.child(b"plugin.crt"),
                                       certificates_path.child(b"plugin.key"))

        self._create_listening_directory(PLUGIN_PATH.parent())

        # Get the node UUID, and then start up:
        getting_id = flocker_client.this_node_uuid()

        def run_service(node_id):
            endpoint = serverFromString(
                reactor, "unix:{}:mode=600".format(PLUGIN_PATH.path))
            service = StreamServerEndpointService(endpoint, Site(
                VolumePlugin(reactor, flocker_client, node_id).app.resource()))
            return main_for_service(reactor, service)
        getting_id.addCallback(run_service)
        return getting_id


def docker_plugin_main():
    """
    Script entry point that runs the Docker plugin.
    """
    return FlockerScriptRunner(script=DockerPluginScript(),
                               options=DockerPluginOptions()).main()
