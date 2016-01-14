# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for AWS CloudFormation installer.
"""

from datetime import timedelta
import json
from itertools import repeat
import os
from subprocess import check_call, check_output
import time

from twisted.internet import reactor
from twisted.internet.defer import maybeDeferred
from twisted.internet.error import ProcessTerminated
from twisted.python.filepath import FilePath
from eliot import Message


from ...common.runner import run_ssh
from ...common import gather_deferreds, loop_until, retry_failure
from ...testtools import AsyncTestCase, async_runner
from ..testtools import Cluster, ControlService
from ...ca import treq_with_authentication, UserCredential
from ...apiclient import FlockerClient
from ...control.httpapi import REST_API_PORT


COMPOSE_NODE0 = '/home/ubuntu/postgres/docker-compose-node0.yml'
COMPOSE_NODE1 = '/home/ubuntu/postgres/docker-compose-node1.yml'
RECREATE_STATEMENT = 'create table test(i int);'
INSERT_STATEMENT = 'insert into test values(1);'
SELECT_STATEMENT = 'select count(*) from test;'

CLOUDFORMATION_STACK_NAME = 'testinstallerstack'
S3_CLOUDFORMATION_TEMPLATE = (
    'https://s3.amazonaws.com/'
    'installer.downloads.clusterhq.com/flocker-cluster.cloudformation.json'
)
POSTGRESQL_PORT = 5432
POSTGRESQL_USERNAME = 'flocker'
POSTGRESQL_PASSWORD = 'flocker'


def remote_command(client_ip, command):
    process_output = []
    d = run_ssh(
        reactor,
        'ubuntu',
        client_ip,
        command,
        handle_stdout=process_output.append
    )
    d.addCallback(
        lambda process_result: (process_result, process_output)
    )
    return d


def remote_docker(client_ip, docker_host, *args):
    return remote_command(
        client_ip,
        ('DOCKER_TLS_VERIFY=1', 'DOCKER_HOST={}'.format(docker_host),
         'docker') + args,
    )


def remote_docker_compose(client_ip, docker_host, compose_file_path, *args):
    return remote_command(
        client_ip,
        ('DOCKER_TLS_VERIFY=1', 'DOCKER_HOST={}'.format(docker_host),
         'docker-compose', '--file', compose_file_path) + args,
    )


def remote_postgres(client_ip, host, command):
    return remote_command(
        client_ip,
        ('psql',
         'postgres://' + POSTGRESQL_USERNAME + ':' + POSTGRESQL_PASSWORD +
         '@' + host + ':' + str(POSTGRESQL_PORT),
         '--command={}'.format(command)),
    )


def get_stack_report(stack_id):
    output = check_output(
        ['aws', 'cloudformation', 'describe-stacks',
         '--stack-name', stack_id]
    )
    results = json.loads(output)
    return results['Stacks'][0]


def wait_for_stack_status(stack_id, target_status):
    def predicate():
        stack_report = get_stack_report(stack_id)
        current_status = stack_report['StackStatus']
        if current_status == target_status:
            return stack_report

    return loop_until(reactor, predicate, repeat(1, 600))


def create_cloudformation_stack(access_key_id, secret_access_key, parameters):
    """
    """
    # Request stack creation.
    stack_name = CLOUDFORMATION_STACK_NAME + str(int(time.time()))
    output = check_output(
        ['aws', 'cloudformation', 'create-stack',
         '--parameters', json.dumps(parameters),
         '--stack-name', stack_name,
         '--template-url', S3_CLOUDFORMATION_TEMPLATE]
    )

    output = json.loads(output)
    stack_id = output['StackId']
    Message.new(cloudformation_stack_id=stack_id)
    return wait_for_stack_status(stack_id, 'CREATE_COMPLETE')


def delete_cloudformation_stack(stack_id):
    """
    """
    result = get_stack_report(stack_id)
    outputs = result['Outputs']
    s3_bucket_name = get_output(outputs, 'S3BucketName')
    check_call(
        ['aws', 's3', 'rb', 's3://{}'.format(s3_bucket_name), '--force']
    )

    check_call(
        ['aws', 'cloudformation', 'delete-stack',
         '--stack-name', stack_id]
    )

    return wait_for_stack_status(stack_id, 'DELETE_COMPLETE')


def get_output(outputs, key):
    for output in outputs:
        if output['OutputKey'] == key:
            return output['OutputValue']

STACK_VARIABLES = {
    'client_node_ip': 'ClientNodeIP',
    'agent_node1_ip': 'AgentNode1IP',
    'agent_node2_ip': 'AgentNode2IP',
    'control_node_ip': 'ControlNodeIP',
}


class DockerComposeTests(AsyncTestCase):
    """
    Tests for AWS CloudFormation installer.
    """
    run_tests_with = async_runner(timeout=timedelta(minutes=20))

    def _stack_from_environment(self):
        for variable_name in STACK_VARIABLES.keys():
            setattr(self, variable_name, os.environ[variable_name.upper()])
        return True

    def __new_stack(self):
        access_key_id = os.environ['ACCESS_KEY_ID']
        secret_access_key = os.environ['SECRET_ACCESS_KEY']
        parameters = [
            {
                'ParameterKey': 'KeyName',
                'ParameterValue': os.environ['KEY_NAME']
            },
            {
                'ParameterKey': 'AccessKeyID',
                'ParameterValue': os.environ['ACCESS_KEY_ID']
            },
            {
                'ParameterKey': 'SecretAccessKey',
                'ParameterValue': os.environ['SECRET_ACCESS_KEY']
            }
        ]

        d = create_cloudformation_stack(
            access_key_id, secret_access_key, parameters
        )
        d.addCallback(
            self.addCleanup, delete_cloudformation_stack, self.stack_id
        )

        def set_stack_variables(stack_report):
            outputs = stack_report['Outputs']
            self.stack_id = stack_report['StackId']
            for variable_name, stack_output_name in STACK_VARIABLES.items():
                setattr(
                    self, variable_name, get_output(outputs, stack_output_name)
                )
        d.addCallback(set_stack_variables)
        return d

    def setUp(self):
        d = maybeDeferred(super(DockerComposeTests, self).setUp)

        def setup_for_stack(ignored):
            if not self._stack_from_environment():
                return self._new_stack()
            self.docker_host = 'tcp://' + self.control_node_ip + ':2376'
            self.addCleanup(self._cleanup_flocker)
            self.addCleanup(self._cleanup_compose)
        d.addCallback(setup_for_stack)
        return d

    def _cleanup_flocker(self):
        local_certs_path = self.mktemp()
        check_call(
            ['scp', '-o', 'StrictHostKeyChecking no', '-r',
             'ubuntu@{}:/etc/flocker'.format(self.client_node_ip),
             local_certs_path]
        )
        certificates_path = FilePath(local_certs_path)
        cluster_cert = certificates_path.child(b"cluster.crt")
        user_cert = certificates_path.child(b"user1.crt")
        user_key = certificates_path.child(b"user1.key")
        user_credential = UserCredential.from_files(user_cert, user_key)
        cluster = Cluster(
            control_node=ControlService(
                public_address=self.control_node_ip.encode("ascii")),
            nodes=[],
            treq=treq_with_authentication(
                reactor, cluster_cert, user_cert, user_key),
            client=FlockerClient(
                reactor, self.control_node_ip.encode("ascii"),
                REST_API_PORT, cluster_cert, user_cert, user_key
            ),
            certificates_path=certificates_path,
            cluster_uuid=user_credential.cluster_uuid,
        )
        return cluster.clean_nodes()

    def _cleanup_compose(self):
        d_node1_compose = remote_docker_compose(
            self.client_node_ip,
            self.docker_host,
            COMPOSE_NODE0, 'stop'
        )
        d_node1_compose.addCallback(
            lambda ignored: remote_docker_compose(
                self.client_node_ip,
                self.docker_host,
                COMPOSE_NODE0, 'rm', '-f'
            )
        )

        d_node2_compose = remote_docker_compose(
            self.client_node_ip, self.docker_host, COMPOSE_NODE1, 'stop'
        )
        d_node2_compose.addCallback(
            lambda ignored: remote_docker_compose(
                self.client_node_ip, self.docker_host, COMPOSE_NODE1,
                'rm', '-f'
            )
        )
        return gather_deferreds([d_node1_compose, d_node2_compose])

    def _wait_for_postgres(self, server_ip):
        def trap(failure):
            failure.trap(ProcessTerminated)
            # psql returns 0 to the shell if it finished normally, 1 if a fatal
            # error of its own occurs (e.g. out of memory, file not found), 2
            # if the connection to the server went bad and the session was not
            # interactive, and 3 if an error occurred in a script and the
            # variable ON_ERROR_STOP was set.
            # http://www.postgresql.org/docs/9.3/static/app-psql.html
            if failure.value.exitCode == 2:
                return False
            else:
                return failure

        def predicate():
            d = remote_postgres(
                self.client_node_ip, server_ip, 'SELECT 1'
            )
            d.addErrback(trap)
            return d

        return loop_until(
            reactor,
            predicate,
            repeat(10, 12)
        )

    def test_docker_compose_up_postgres(self):
        """
        """
        def pull_postgres():
            return remote_docker(
                self.client_node_ip,
                self.docker_host,
                'pull', 'postgres:latest'
            )
        d = retry_failure(
            reactor=reactor,
            function=pull_postgres,
            expected=(ProcessTerminated,),
            steps=repeat(1, 5)
        )
        d.addCallback(
            lambda ignored: remote_docker_compose(
                self.client_node_ip,
                self.docker_host,
                COMPOSE_NODE0, 'up', '-d'
            )
        )
        d.addCallback(
            lambda ignored: self._wait_for_postgres(self.agent_node1_ip)
        )
        d.addCallback(
            lambda ignored: remote_postgres(
                self.client_node_ip, self.agent_node1_ip,
                RECREATE_STATEMENT + INSERT_STATEMENT
            )
        )

        d.addCallback(
            lambda ignored: remote_postgres(
                self.client_node_ip, self.agent_node1_ip, SELECT_STATEMENT
            )
        )

        d.addCallback(
            lambda ignored: remote_docker_compose(
                self.client_node_ip, self.docker_host, COMPOSE_NODE0, 'stop'
            )
        )

        d.addCallback(
            lambda ignored: remote_docker_compose(
                self.client_node_ip, self.docker_host,
                COMPOSE_NODE0, 'rm', '--force'
            )
        )

        d.addCallback(
            lambda ignored: remote_docker_compose(
                self.client_node_ip, self.docker_host,
                COMPOSE_NODE1, 'up', '-d'
            )
        )

        d.addCallback(
            lambda ignored: self._wait_for_postgres(self.agent_node2_ip)
        )

        d.addCallback(
            lambda ignored: remote_postgres(
                self.client_node_ip,
                self.agent_node2_ip, SELECT_STATEMENT
            )
        )

        d.addCallback(
            lambda (process_status, process_output): self.assertEqual(
                "1", process_output[2].strip()
            )
        )

        return d
