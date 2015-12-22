# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for AWS CloudFormation installer.
"""

import os

from twisted.internet import reactor
from twisted.internet.defer import maybeDeferred

from ...common.runner import run_ssh
from ...common import gather_deferreds
from ...testtools import AsyncTestCase

CLIENT_IP = os.environ['CLIENT_IP']
DOCKER_HOST = os.environ['DOCKER_HOST']
NODE0 = os.environ['CLUSTER_NODE0']
NODE1 = os.environ['CLUSTER_NODE1']
COMPOSE_NODE0 = '/home/ubuntu/postgres/docker-compose-node0.yml'
COMPOSE_NODE1 = '/home/ubuntu/postgres/docker-compose-node1.yml'

RECREATE_STATEMENT = 'drop table if exists test; create table test(i int);'
INSERT_STATEMENT = 'insert into test values(1);'
SELECT_STATEMENT = 'select count(*) from test;'


def remote_command(node, *args):
    command_output = []
    d = run_ssh(
        reactor,
        'ubuntu',
        node,
        args,
        handle_stdout=command_output.append
    )
    d.addCallback(
        lambda process_result: (process_result, command_output)
    )
    return d


def remote_docker_compose(compose_file_path, *args):
    docker_compose_output = []
    d = run_ssh(
        reactor,
        'ubuntu',
        CLIENT_IP,
        ('DOCKER_HOST={}'.format(DOCKER_HOST),
         'docker-compose', '--file', compose_file_path) + args,
        handle_stdout=docker_compose_output.append
    )
    d.addCallback(
        lambda process_result: (process_result, docker_compose_output)
    )
    return d


def remote_postgres(host, command):
    postgres_output = []
    d = run_ssh(
        reactor,
        'ubuntu',
        CLIENT_IP,
        ('psql', 'postgres://flocker:flocker@' + host + ':5432',
         '--command={}'.format(command)),
        handle_stdout=postgres_output.append
    )
    d.addCallback(
        lambda process_result: (process_result, postgres_output)
    )
    return d


class DockerComposeTests(AsyncTestCase):
    """
    Tests for AWS CloudFormation installer.
    """

    def setUp(self):
        d = maybeDeferred(super(DockerComposeTests, self).setUp)

        def local_setup(ignored):
            d_node1_compose = remote_docker_compose(COMPOSE_NODE0, 'stop')
            d_node1_compose.addCallback(
                lambda ignored: remote_docker_compose(
                    COMPOSE_NODE0, 'rm', '-f'
                )
            )

            d_node1_docker = remote_command(NODE0, 'sudo', 'docker', 'stop',
                                            'postgres_postgres_1')
            d_node1_docker.addCallback(
                lambda ignored: remote_command(
                    NODE0, 'sudo', 'docker', 'rmi', '-f', 'postgres_postgres_1'
                )
            )

            d_node2_compose = remote_docker_compose(COMPOSE_NODE1, 'stop')
            d_node2_compose.addCallback(
                lambda ignored: remote_docker_compose(
                    COMPOSE_NODE1, 'rm', '-f'
                )
            )

            d_node2_docker = remote_command(NODE1, 'sudo', 'docker', 'stop',
                                            'postgres_postgres_1')
            d_node1_docker.addCallback(
                lambda ignored: remote_command(
                    NODE1, 'sudo', 'docker', 'rmi', '-f', 'postgres_postgres_1'
                )
            )

            return gather_deferreds([d_node1_compose, d_node1_docker,
                                     d_node2_compose, d_node2_docker])
        # d.addCallback(local_setup)
        return d

    def test_docker_compose_up_postgres(self):
        """
        """
        d = remote_docker_compose(COMPOSE_NODE0, 'up', '-d')

        d.addCallback(
            lambda ignored: remote_postgres(
                NODE0, RECREATE_STATEMENT + INSERT_STATEMENT
            )
        )

        d.addCallback(
            lambda ignored: remote_postgres(
                NODE0, SELECT_STATEMENT
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

        d.addCallback(
            lambda ignored: remote_docker_compose(
                COMPOSE_NODE1, 'up', '-d'
            )
        )

        d.addCallback(
            lambda ignored: remote_postgres(
                NODE1, SELECT_STATEMENT
            )
        )

        d.addCallback(
            lambda (process_status, process_output): self.assertEqual(
                "1", process_output[2].strip()
            )
        )

        return d
