# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for the Flocker Docker plugin.
"""

import ssl
from twisted.trial.unittest import TestCase

from docker import Client
from docker.tls import TLSConfig
from docker.utils import create_host_config

from ...testtools import random_name
from ..testtools import (
    require_cluster, post_http_server, assert_http_server,
)
from ..scripts import SCRIPTS

DOCKER_PORT = 2376


class DockerPluginTests(TestCase):
    """
    Tests for the Docker plugin.
    """
    def client(self, cluster, address):
        """
        Open a Docker client to the given address.

        :param Cluster cluster: Description of the cluster we're talking to.
        :param bytes address: The public IP of the node to connect to.

        :return: Docker ``Client`` instance.
        """
        def get_path(name):
            return cluster.certificates_path.child(name).path

        tls = TLSConfig(
            client_cert=(get_path(b"user.crt"), get_path(b"user.key")),
            # Blows up if not set
            # (https://github.com/shazow/urllib3/issues/695):
            ssl_version=ssl.PROTOCOL_TLSv1,
            # Don't validate hostname, we don't generate it correctly, but
            # do verify certificate authority signed the server certificate:
            assert_hostname=False,
            verify=get_path(b"cluster.crt"))
        return Client(base_url="https://{}:{}".format(address, DOCKER_PORT),
                      tls=tls, timeout=100)

    def run_python_container(self, cluster, address, docker_arguments, script,
                             script_arguments, cleanup=True):
        """
        Run a Python script as a Docker container with the Flocker volume
        driver.

        This is a blocking call.

        :param Cluster cluster: Description of the cluster we're talking to.
        :param bytes address: The public IP of the node where it will run.
        :param dict docker_arguments: Additional arguments to pass to
            Docker ``create_container()`` call.
        :param FilePath script: The script to run.
        :param list script_arguments: Additional arguments to pass to the
            script.
        :param cleanup: If true, cleanup the container at test end.

        :return: Container id, once the Docker container has started.
        """
        client = self.client(cluster, address)

        # Remove all existing containers on the node, in case they're left
        # over from previous test:
        for container in client.containers():
            client.remove_container(container["Id"], force=True)

        container = client.create_container(
            "python:2.7-slim",
            ["python", "-c", script.getContent()] + list(script_arguments),
            volume_driver="flocker", **docker_arguments)
        cid = container["Id"]
        client.start(container=cid)
        if cleanup:
            self.addCleanup(client.remove_container, cid, force=True)
        return cid

    @require_cluster(1)
    def test_run_container_with_volume(self, cluster):
        """
        Docker can run a container with a volume provisioned by Flocker.
        """
        data = random_name(self).encode("utf-8")
        node = cluster.nodes[0]
        http_port = 8080

        volume_name = random_name(self)
        self.run_python_container(
            cluster, node.public_address,
            {"host_config": create_host_config(
                binds=["{}:/data".format(volume_name)],
                port_bindings={http_port: http_port}),
             "ports": [http_port]},
            SCRIPTS.child(b"datahttp.py"),
            # This tells the script where it should store its data,
            # and we want it to specifically use the volume:
            [u"/data"])

        d = post_http_server(self, node.public_address, http_port,
                             {"data": data})
        d.addCallback(lambda _: assert_http_server(
            self, node.public_address, http_port, expected_response=data))
        return d

    def _test_move(self, cluster, origin_node, destination_node):
        """
        Assert that Docker can run a container with a volume provisioned by
        Flocker, shut down the container and then start a new container
        with the same volume on the specified node.

        :param cluster: The ``Cluster`` to talk to.
        :param Node origin_node: Original node to start container on.
        :param Node destination_node: Original node to start container on.

        :return: ``Deferred`` that fires on assertion success, or failure.
        """
        data = "hello world"
        http_port = 8080
        volume_name = random_name(self)
        container_args = {
            "host_config": create_host_config(
                binds=["{}:/data".format(volume_name)],
                port_bindings={http_port: http_port}),
            "ports": [http_port]}

        cid = self.run_python_container(
            cluster, origin_node.public_address, container_args,
            SCRIPTS.child(b"datahttp.py"),
            # This tells the script where it should store its data,
            # and we want it to specifically use the volume:
            [u"/data"], cleanup=False)

        # Post to container on origin node:
        d = post_http_server(self, origin_node.public_address, http_port,
                             {"data": data})

        def posted(_):
            # Shutdown original container:
            self.client(cluster, origin_node.public_address).remove_container(
                cid, force=True)
            # Start container on destination node with same volume:
            self.run_python_container(
                cluster, destination_node.public_address, container_args,
                SCRIPTS.child(b"datahttp.py"), [u"/data"])
        d.addCallback(posted)
        d.addCallback(lambda _: assert_http_server(
            self, destination_node.public_address, http_port,
            expected_response=data))
        return d

    @require_cluster(1)
    def test_move_volume_single_node(self, cluster):
        """
        Docker can run a container with a volume provisioned by Flocker, shut
        down the container and then start a new container with the same
        volume on the same machine.
        """
        return self._test_move(cluster, cluster.nodes[0], cluster.nodes[0])

    @require_cluster(2)
    def test_move_volume_different_node(self, cluster):
        """
        Docker can run a container with a volume provisioned by Flocker, shut
        down the container and then start a new container with the same
        volume on a different machine.
        """
        return self._test_move(cluster, cluster.nodes[0], cluster.nodes[1])
