# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for the Flocker Docker plugin.
"""

from twisted.trial.unittest import TestCase

from docker import Client
from docker.tls import TLSConfig
from docker.utils import create_host_config

from ...testtools import random_name
from ..testtools import (
    require_cluster, post_http_server, assert_http_server,
)
from ..obsolete.test_containers import CURRENT_DIRECTORY


class DockerPluginTests(TestCase):
    """
    Tests for the Docker plugin.
    """
    def run_python_container(self, cluster, address, docker_arguments, script,
                             script_arguments):
        """
        Run a Python script as a Docker container.

        This is a blocking call.

        :param Cluster cluster: Description of the cluster we're talking to.
        :param bytes address: The public IP of the node where it will run.
        :param dict docker_arguments: Additional arguments to pass to
            Docker run call.
        :param FilePath script: The script to run.
        :param list script_arguments: Additional arguments to pass to the
            script.

        :return: When Docker container has started.
        """
        def get_path(name):
            return cluster.certificates_path.child(name).path

        tls = TLSConfig(
            ca_cert=get_path(b"cluster.crt"),
            client_cert=(get_path(b"user.crt"), get_path(b"user.key")),
            # Don't validate hostname, we don't generate it correctly:
            assert_hostname=False)
        client = Client(base_url="https://{}:2376/", tls=tls)
        container = client.create_container(
            "python2.7:slim",
            ["python", "-c", script.getContent()] + list(script_arguments),
            **docker_arguments)
        client.start(container=container["Id"])
        self.addCleanup(client.remove, container["Id"], force=True)

    @require_cluster(1)
    def test_run_container_with_volume(self, cluster):
        """
        Docker can run a container with a volume provisioned by Flocker.
        """
        data = "hello world"
        node = cluster.nodes[0]

        volume_name = random_name()
        self.run_python_container(
            cluster, node.public_address,
            dict(host_config=create_host_config(
                binds=["{}:/data".format(volume_name)])),
            CURRENT_DIRECTORY.child(b"datahttp.py"),
            [u"/data"])

        d = post_http_server(self, node.public_address, 8080, {"data": data})
        d.addCallback(lambda _: assert_http_server(
            self, node.public_address, 8080, expected_response=data))
        return d
