# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for AWS CloudFormation installer.
"""

from datetime import timedelta
import json
from itertools import repeat
import os
from subprocess import check_output
import time

from twisted.internet import reactor
from twisted.internet.defer import maybeDeferred
from twisted.internet.error import ProcessTerminated
from twisted.python.filepath import FilePath

from eliot import Message

from ...common.runner import run_ssh
from ...common import gather_deferreds, loop_until, retry_failure
from ...testtools import AsyncTestCase, async_runner, random_name
from ..testtools import connected_cluster


RECREATE_STATEMENT = 'create table test(i int);'
INSERT_STATEMENT = 'insert into test values(1);'
SELECT_STATEMENT = 'select count(*) from test;'

CLOUDFORMATION_STACK_NAME = 'testinstallerstack'

POSTGRESQL_PORT = 5432
POSTGRESQL_USERNAME = 'flocker'
POSTGRESQL_PASSWORD = 'flocker'


def remote_command(client_ip, command):
    """
    Run ``command`` on ``client_ip``.

    :returns: A ``Deferred`` when the command has completed or failed.
    """
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
    """
    Run ``docker`` on ``client_ip``.

    :param bytes docker_host: The DOCKER_HOST environment variable to set
        before running ``docker``.
    :param args: Other command line arguments to supply to ``docker``.
    :returns: A ``Deferred`` when the command has completed or failed.
    """
    return remote_command(
        client_ip,
        ('DOCKER_TLS_VERIFY=1', 'DOCKER_HOST={}'.format(docker_host),
         'docker') + args,
    )


def remote_docker_compose(client_ip, docker_host, compose_file_path, *args):
    """
    Run ``docker-compose`` on ``client_ip``.

    :param bytes docker_host: The DOCKER_HOST environment variable to set
        before running ``docker-compose``.
    :param unicode compose_file_path: The absolute path to a ``docker-compose``
        template file.
    :param args: Other command line arguments to supply to ``docker-compose``.
    :returns: A ``Deferred`` when the command has completed or failed.
    """
    return remote_command(
        client_ip,
        ('DOCKER_TLS_VERIFY=1', 'DOCKER_HOST={}'.format(docker_host),
         'docker-compose', '--file', compose_file_path) + args,
    )


def remote_postgres(client_ip, host, command):
    """
    Run ``psql`` on ``client_ip``.

    :param bytes host: The IP address of the PostgreSQL server to connect to.
    :param unicode command: The command to run on the server.
    :returns: A ``Deferred`` when the command has completed or failed.
    """
    return remote_command(
        client_ip,
        ('psql',
         'postgres://' + POSTGRESQL_USERNAME + ':' + POSTGRESQL_PASSWORD +
         '@' + host + ':' + str(POSTGRESQL_PORT),
         '--command={}'.format(command)),
    )


def get_stack_report(stack_id):
    """
    Get information about a CloudFormation stack.

    :param unicode stack_id: The AWS cloudformation stack ID.
    :returns: A ``dict`` of information about the stack.
    """
    output = check_output(
        ['aws', 'cloudformation', 'describe-stacks',
         '--stack-name', stack_id]
    )
    results = json.loads(output)
    return results['Stacks'][0]


def wait_for_stack_status(stack_id, target_status):
    """
    Poll the status of a CloudFormation stack.

    :param unicode stack_id: The AWS cloudformation stack ID.
    :param unicode target_status: The desired stack status.
    :returns: A ``Deferred`` which fires when the stack has ``target_status``.
    """
    Message.log(
        function='wait_for_stack_status',
        stack_id=stack_id,
        target_status=target_status,
    )

    def predicate():
        stack_report = get_stack_report(stack_id)
        current_status = stack_report['StackStatus']
        if current_status == target_status:
            return stack_report

    return loop_until(reactor, predicate, repeat(10, 60))


def create_cloudformation_stack(template_url, access_key_id,
                                secret_access_key, parameters):
    """
    Create a CloudFormation stack.

    :param unicode stack_id: The AWS cloudformation stack ID.
    :returns: A ``Deferred`` which fires when the stack has been created.
    """
    # Request stack creation.
    stack_name = CLOUDFORMATION_STACK_NAME + str(int(time.time()))
    output = check_output(
        ['aws', 'cloudformation', 'create-stack',
         '--disable-rollback',
         '--parameters', json.dumps(parameters),
         '--stack-name', stack_name,
         '--template-url', template_url]
    )
    output = json.loads(output)
    stack_id = output['StackId']
    Message.new(cloudformation_stack_id=stack_id)
    return wait_for_stack_status(stack_id, 'CREATE_COMPLETE')


def delete_cloudformation_stack(stack_id):
    """
    Delete a CloudFormation stack.

    :param unicode stack_id: The AWS cloudformation stack ID.
    :returns: A ``Deferred`` which fires when the stack has been deleted.
    """
    result = get_stack_report(stack_id)
    outputs = result['Outputs']
    s3_bucket_name = get_output(outputs, 'S3Bucket')
    check_output(
        ['aws', 's3', 'rb', 's3://{}'.format(s3_bucket_name), '--force']
    )

    check_output(
        ['aws', 'cloudformation', 'delete-stack',
         '--stack-name', stack_id]
    )

    return wait_for_stack_status(stack_id, 'DELETE_COMPLETE')


def get_output(outputs, key):
    """
    Parse and return values from a CloudFormation outputs list.

    :param list outputs: A list of ``dict`` having items of `(`OutputKey``,
        ``OutputValue``).
    :param unicode key: The key for which to retrieve a value from ``outputs``.
    :returns: A ``unicode`` value.
    """
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
        """
        Look for environment variables describing an existing stack but skip
        the test unless *all* the required variables are supplied.
        """
        found = {}
        for variable_name in STACK_VARIABLES.keys():
            value = os.environ.get(variable_name.upper(), None)
            if value is not None:
                found[variable_name] = value
                setattr(self, variable_name, value)

        if found:
            missing_keys = set(STACK_VARIABLES.keys()) - set(found.keys())
            if missing_keys:
                raise Exception('Missing Keys', missing_keys)
            else:
                return True
        else:
            return False

    def _new_stack(self):
        """
        Create a new CloudFormation stack from a template URL supplied as an
        environment variable. AWS credentials and CloudFormation parameter
        values must also be supplied as environment variables.
        """
        template_url = os.environ.get('CLOUDFORMATION_TEMPLATE_URL')
        if template_url is None:
            self.skipTest(
                'CLOUDFORMATION_TEMPLATE_URL environment variable not found. '
            )
        access_key_id = os.environ['ACCESS_KEY_ID']
        secret_access_key = os.environ['SECRET_ACCESS_KEY']
        parameters = [
            {
                'ParameterKey': 'KeyPair',
                'ParameterValue': os.environ['KEY_PAIR']
            },
            {
                'ParameterKey': 'AccessKeyID',
                'ParameterValue': os.environ['ACCESS_KEY_ID']
            },
            {
                'ParameterKey': 'SecretAccessKey',
                'ParameterValue': os.environ['SECRET_ACCESS_KEY']
            },
            {
                'ParameterKey': 'VolumeHubToken',
                'ParameterValue': os.environ['VOLUMEHUB_TOKEN']
            }
        ]

        d = create_cloudformation_stack(
            template_url,
            access_key_id, secret_access_key, parameters
        )

        def set_stack_variables(stack_report):
            outputs = stack_report['Outputs']
            stack_id = stack_report['StackId']
            for variable_name, stack_output_name in STACK_VARIABLES.items():
                setattr(
                    self, variable_name, get_output(outputs, stack_output_name)
                )
            if 'KEEP_STACK' not in os.environ:
                self.addCleanup(delete_cloudformation_stack, stack_id)
        d.addCallback(set_stack_variables)
        return d

    def setUp(self):
        """
        Create a new stack or configure the test to operate on an existing
        stack if the environment contains all the necessary IP addresses.
        """
        d = maybeDeferred(super(DockerComposeTests, self).setUp)

        def setup_stack(ignored):
            if not self._stack_from_environment():
                return self._new_stack()
        d.addCallback(setup_stack)

        def stack_ready(ignored):
            self.docker_host = 'tcp://' + self.control_node_ip + ':2376'
            self.addCleanup(self._cleanup_flocker)
            self.addCleanup(self._cleanup_compose)
        d.addCallback(stack_ready)

        return d

    def _cleanup_flocker(self):
        """
        Cleanup any Flocker volumes that were created during the tests.
        """
        local_certs_path = FilePath(self.mktemp())
        # Download the Flocker certificates from the client node so that we can
        # connect to the control service from the machine running the tests.
        # XXX Perhaps it'd be better to have a cluster cleanup tool available
        # on the client which can also be run by people who are attempting the
        # tutorial.
        check_output(
            ['scp', '-o', 'StrictHostKeyChecking no', '-r',
             'ubuntu@{}:/etc/flocker'.format(self.client_node_ip),
             local_certs_path.path]
        )
        d = connected_cluster(
            reactor=reactor,
            control_node=self.control_node_ip.encode('ascii'),
            certificates_path=local_certs_path,
            num_agent_nodes=2,
            hostname_to_public_address={},
            username='user1',
        )
        d.addCallback(
            lambda cluster: cluster.clean_nodes(
                remove_foreign_containers=False
            )
        )
        return d

    def _cleanup_compose(self):
        """
        Run docker-compose stop and rm -f for both demo templates to stop and
        remove all the containers that were created during the test.
        Run serially because docker-compose + swarm sometimes fail when
        commands are run in parallel.
        """
        d_node1_compose = remote_docker_compose(
            self.client_node_ip,
            self.docker_host,
            self.compose_node1, 'stop'
        )
        d_node1_compose.addCallback(
            lambda ignored: remote_docker_compose(
                self.client_node_ip,
                self.docker_host,
                self.compose_node1, 'rm', '-f'
            ).addErrback(
                # This sometimes fails with exit code 255
                # and a message ValueError: No JSON object could be decoded
                lambda failure: failure.trap(ProcessTerminated)
            )
        )
        d_node2_compose = remote_docker_compose(
            self.client_node_ip,
            self.docker_host,
            self.compose_node2,
            'stop',
        )
        d_node2_compose.addCallback(
            lambda ignored: remote_docker_compose(
                self.client_node_ip,
                self.docker_host,
                self.compose_node2,
                'rm', '-f'
            ).addErrback(
                # This sometimes fails with exit code 255
                # and a message ValueError: No JSON object could be decoded
                lambda failure: failure.trap(ProcessTerminated)
            )
        )
        return gather_deferreds([d_node1_compose, d_node2_compose])

    def _wait_for_postgres(self, server_ip):
        """
        Try to connect to the PostgreSQL server at ``server_ip`` once per
        second until the server responds.

        :param bytes server_ip: The IP address of the PostgreSQL server.
        :returns: The result of the query if the query succeeds.
        :raises: LoopExceeded if the query does not succeed after 10 connection
            attempts.
        """
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
            repeat(1, 10)
        )

    def test_docker_compose_up_postgres(self):
        """
        A Flocker cluster, built using the CloudFormation template, has a
        client node. That node has ``docker-compose`` and templates. The first
        template creates a PostgreSQL server on one node. The second template
        moves the PostgreSQL server to the second node.
        """
        remote_compose_directory = random_name(self)
        # Publish the compose files to the client.
        command = [
            'scp', '-o', 'StrictHostKeyChecking no', '-r',
            FilePath(__file__).parent().descendant(
                ['installer', 'postgres']
            ).path,
            'ubuntu@{}:{}'.format(
                self.client_node_ip,
                remote_compose_directory
            )
        ]
        check_output(command)

        self.compose_node1 = (
            remote_compose_directory + "/docker-compose-node1.yml"
        )
        self.compose_node2 = (
            remote_compose_directory + "/docker-compose-node2.yml"
        )

        # This isn't in the tutorial, but docker-compose doesn't retry failed
        # pulls and pulls fail all the time.
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
        # Create the PostgreSQL server on node1. A Flocker dataset will be
        # created and attached by way of the Flocker Docker plugin.
        d.addCallback(
            lambda ignored: remote_docker_compose(
                self.client_node_ip,
                self.docker_host,
                self.compose_node1, 'up', '-d'
            )
        )
        # Docker-compose blocks until the container is running but the the
        # PostgreSQL server may not be ready to receive connections.
        d.addCallback(
            lambda ignored: self._wait_for_postgres(self.agent_node1_ip)
        )
        # Create a database and insert a record.
        d.addCallback(
            lambda ignored: remote_postgres(
                self.client_node_ip, self.agent_node1_ip,
                RECREATE_STATEMENT + INSERT_STATEMENT
            )
        )
        # Stop and then remove the container
        d.addCallback(
            lambda ignored: remote_docker_compose(
                self.client_node_ip,
                self.docker_host,
                self.compose_node1,
                'stop'
            )
        )
        # Unless you remove the container, Swarm will refuse to start a new
        # container on the other node.
        d.addCallback(
            lambda ignored: remote_docker_compose(
                self.client_node_ip, self.docker_host,
                self.compose_node1, 'rm', '--force'
            )
        )
        # Start the container on the other node.
        d.addCallback(
            lambda ignored: remote_docker_compose(
                self.client_node_ip, self.docker_host,
                self.compose_node2, 'up', '-d'
            )
        )
        # The database server won't be immediately ready to receive
        # connections.
        d.addCallback(
            lambda ignored: self._wait_for_postgres(self.agent_node2_ip)
        )
        # Select the record
        d.addCallback(
            lambda ignored: remote_postgres(
                self.client_node_ip,
                self.agent_node2_ip, SELECT_STATEMENT
            )
        )
        # There should be a record and the value should be 1.
        d.addCallback(
            lambda (process_status, process_output): self.assertEqual(
                "1", process_output[2].strip()
            )
        )

        return d
