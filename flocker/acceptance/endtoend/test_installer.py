# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for AWS CloudFormation installer.
"""

from datetime import timedelta
import os
from subprocess import check_call, check_output

from twisted.internet import reactor
from twisted.internet.task import deferLater
from twisted.internet.defer import maybeDeferred

from twisted.python.filepath import FilePath
from eliot import Message


from ...common.runner import run_ssh
from ...common import gather_deferreds
from ...testtools import AsyncTestCase, async_runner
from ..testtools import Cluster, ControlService
from ...ca import treq_with_authentication, UserCredential
from ...apiclient import FlockerClient
from ...control.httpapi import REST_API_PORT

CLIENT_IP = os.environ['CLIENT_IP']
DOCKER_HOST = os.environ['DOCKER_HOST']
NODE0 = os.environ['CLUSTER_NODE0']
NODE1 = os.environ['CLUSTER_NODE1']
COMPOSE_NODE0 = '/home/ubuntu/postgres/docker-compose-node0.yml'
COMPOSE_NODE1 = '/home/ubuntu/postgres/docker-compose-node1.yml'

RECREATE_STATEMENT = 'drop table if exists test; create table test(i int);'
INSERT_STATEMENT = 'insert into test values(1);'
SELECT_STATEMENT = 'select count(*) from test;'

CLOUDFORMATION_STACK_NAME = 'test_installer_stack'
S3_CLOUDFORMATION_TEMPLATE = 'https://s3.amazonaws.com/ \
        installer.downloads.clusterhq.com/flocker-cluster.cloudformation.json'


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
    d = deferLater(
        reactor,
        60,
        run_ssh,
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


def cleanup(local_certs_path):
    certificates_path = FilePath(local_certs_path)
    cluster_cert = certificates_path.child(b"cluster.crt")
    user_cert = certificates_path.child(b"user1.crt")
    user_key = certificates_path.child(b"user1.key")
    user_credential = UserCredential.from_files(user_cert, user_key)
    cluster = Cluster(
        control_node=ControlService(public_address=NODE0),
        nodes=[],
        treq=treq_with_authentication(
            reactor, cluster_cert, user_cert, user_key),
        client=FlockerClient(reactor, NODE0, REST_API_PORT,
                             cluster_cert, user_cert, user_key),
        certificates_path=certificates_path,
        cluster_uuid=user_credential.cluster_uuid,
    )
    d_node1_compose = remote_docker_compose(COMPOSE_NODE0, 'stop')
    d_node1_compose.addCallback(
        lambda ignored: remote_docker_compose(
            COMPOSE_NODE0, 'rm', '-f'
        )
    )

    d_node2_compose = remote_docker_compose(COMPOSE_NODE1, 'stop')
    d_node2_compose.addCallback(
        lambda ignored: remote_docker_compose(
            COMPOSE_NODE1, 'rm', '-f'
        )
    )

    d = gather_deferreds([d_node1_compose, d_node2_compose])

    d.addCallback(
        lambda ignored: cluster.clean_nodes()
    )

    d.addCallback(
        lambda ignored: delete_cloudformation_stack
    )
    return d


def create_cloudformation_stack():
    """
    """
    # Request stack creation.
    stack_id = check_output(
        ['aws', 'cloudformation', 'create-stack',
         '--stack-name', CLOUDFORMATION_STACK_NAME,
         '--template-body', S3_CLOUDFORMATION_TEMPLATE]
    )
    Message.new(cloudformation_stack_id=stack_id)


def delete_cloudformation_stack():
    """
    """
    check_call(
        ['aws', 'cloudformation', 'delete-stack',
         '--stack-name', CLOUDFORMATION_STACK_NAME]
    )


class DockerComposeTests(AsyncTestCase):
    """
    Tests for AWS CloudFormation installer.
    """
    run_tests_with = async_runner(timeout=timedelta(minutes=10))

    def setUp(self):
        create_cloudformation_stack()
        local_certs_path = self.mktemp()
        check_call(
            ['scp', '-r',
             'ubuntu@{}:/etc/flocker'.format(CLIENT_IP),
             local_certs_path]
        )
        self.addCleanup(cleanup, local_certs_path)
        d = maybeDeferred(super(DockerComposeTests, self).setUp)
        d.addCallback(lambda ignored: cleanup(local_certs_path))
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
