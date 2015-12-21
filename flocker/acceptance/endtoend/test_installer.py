# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for AWS CloudFormation installer.
"""

import os

from twisted.internet import reactor

from ...common.runner import run_ssh
from ...testtools import AsyncTestCase

CLIENT_IP = os.environ['CLIENT_IP']
DOCKER_HOST = os.environ['DOCKER_HOST']
NODE0 = os.environ['CLUSTER_NODE0']


class DockerComposeTests(AsyncTestCase):
    """
    Tests for AWS CloudFormation installer.
    """
    def test_docker_compose_up_mysql(self):
        """
        """
        compose_node0 = '/home/ubuntu/mysql/docker-compose-node0.yml'
        # MySQL doesn't allow dashes.
        database_name = 'test_docker_compose_up_mysql'

        docker_compose_output = []

        def docker_compose_up():
            return run_ssh(
                reactor,
                'ubuntu',
                CLIENT_IP,
                ['DOCKER_HOST={}'.format(DOCKER_HOST),
                 'docker-compose', '-f', compose_node0, 'up', '-d'],
                handle_stdout=docker_compose_output.append
            )
        d = docker_compose_up()

        mysql_output = []

        def mysql_insert(ignored):
            return run_ssh(
                reactor,
                'ubuntu',
                CLIENT_IP,
                ['mysql', '--host=' + NODE0, '--port=3306',
                 '--user=root', '--password=secret',
                 '--wait',
                 '--execute=create database {}'.format(database_name)],
                handle_stdout=mysql_output.append
            )
        d.addCallback(mysql_insert)

        d.addCallback(
            lambda ignored: self.assertEqual("", mysql_output)
        )

        return d
