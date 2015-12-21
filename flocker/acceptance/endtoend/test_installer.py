# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for AWS CloudFormation installer.
"""

import os
import tarfile

from twisted.internet import reactor
from twisted.python.filepath import FilePath

from ...common.runner import run_ssh, download_file
from ...testtools import AsyncTestCase


class DockerComposeTests(AsyncTestCase):
    """
    Tests for AWS CloudFormation installer.
    """
    def test_docker_compose_up_mysql(self):
        """
        """
        client_ip = os.environ.get('CLIENT_IP')
        docker_host = os.environ.get('DOCKER_HOST')
        node0 = os.environ.get('CLUSTER_NODE0')

        def docker_compose_up():
            docker_compose_output = []
            return run_ssh(
                reactor,
                'ubuntu',
                client_ip,
                ['DOCKER_HOST={}'.format(docker_host), 'docker-compose', '-f', '/home/ubuntu/mysql/docker-compose-node0.yml', 'up', '-d'],
                handle_stdout=docker_compose_output.append
            )

        def mysql_insert(ignored):
            mysql_output = []
            return run_ssh(
                reactor,
                'ubuntu',
                client_ip,
                ['mysql', '--host', node0, '--port', '3306', '--user', 'root', '--password', 'secret', '--wait'],
                handle_stdout=mysql_output.append
            ).addCallback(
                lambda ignored: self.assertEqual("", mysql_output)
            )

        d = docker_compose_up()
        mysql_insert_node0 = d.addCallback(mysql_insert)
        return mysql_insert_node0
