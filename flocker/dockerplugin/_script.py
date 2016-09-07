# Copyright ClusterHQ Inc. See LICENSE file for details.

"""
Command to start up the Docker plugin.
"""
from os import umask
from stat import S_IRUSR, S_IWUSR, S_IXUSR
from uuid import uuid4
import yaml

from twisted.python.usage import Options
from twisted.internet.endpoints import serverFromString
from twisted.application.internet import StreamServerEndpointService
from twisted.web.server import Site
from twisted.python.filepath import FilePath

from ..common.script import (
    flocker_standard_options, FlockerScriptRunner, main_for_service)
from ._api import VolumePlugin
from ..node.script import (
    backend_and_api_args_from_configuration,
    get_api,
)

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
        configuration = yaml.safe_load(
            options[u"agent-config"].getContent()
        )
        (backend_description,
         api_args) = backend_and_api_args_from_configuration(
            configuration['dataset']
        )
        api = get_api(
            backend=backend_description,
            api_args=api_args,
            reactor=reactor,
            cluster_id=uuid4(),
        )
        self._create_listening_directory(PLUGIN_PATH.parent())

        # This is how to run a REST API on a Unix socket.
        endpoint = serverFromString(
            reactor, "unix:{}:mode=600".format(PLUGIN_PATH.path))
        service = StreamServerEndpointService(endpoint, Site(
            VolumePlugin(reactor, api).app.resource()))
        return main_for_service(reactor, service)


def docker_plugin_main():
    """
    Script entry point that runs the Docker plugin.
    """
    return FlockerScriptRunner(script=DockerPluginScript(),
                               options=DockerPluginOptions()).main()
