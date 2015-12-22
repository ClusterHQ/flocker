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
NODE1 = os.environ['CLUSTER_NODE1']
COMPOSE_NODE0 = '/home/ubuntu/mysql/docker-compose-node0.yml'
COMPOSE_NODE1 = '/home/ubuntu/mysql/docker-compose-node1.yml'


class DockerComposeTests(AsyncTestCase):
    """
    Tests for AWS CloudFormation installer.
    """
    def test_docker_compose_up_mysql(self):
        """
        """
        # MySQL doesn't allow dashes.
        database_name = 'test_docker_compose_up_mysql'

        docker_compose_output = []

        def remote_docker_compose(compose_file_path, *args):
            return run_ssh(
                reactor,
                'ubuntu',
                CLIENT_IP,
                ('DOCKER_HOST={}'.format(DOCKER_HOST),
                 'docker-compose', '--file', compose_file_path) + args,
                handle_stdout=docker_compose_output.append
            )
        d = remote_docker_compose(COMPOSE_NODE0, 'up', '-d')

        mysql_output = []

        def remote_mysql(host, command):
            return run_ssh(
                reactor,
                'ubuntu',
                CLIENT_IP,
                ['mysql', '--host=' + host, '--port=3306',
                 '--user=root', '--password=secret',
                 '--wait',
                 '--execute={}'.format(command)],
                handle_stdout=mysql_output.append
            )

        d.addCallback(
            lambda ignored: remote_mysql(
                NODE0, 'create database {}'.format(database_name)
            )
        )

        d.addCallback(
            lambda ignored: remote_docker_compose(COMPOSE_NODE0, 'stop')
        )

        d.addCallback(
            lambda ignored: remote_docker_compose(
                COMPOSE_NODE0, 'rm', '--force'
            )
        )

        d = remote_docker_compose(COMPOSE_NODE1, 'up', '-d')

        d.addCallback(
            lambda ignored: remote_mysql(
                NODE1, 'show databases'
            )
        )

        d.addCallback(
            lambda ignored: self.assertEqual("", mysql_output)
        )

        return d
