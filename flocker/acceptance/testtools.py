# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Testing utilities for ``flocker.acceptance``.
"""

from pipes import quote as shell_quote
from socket import socket
from subprocess import check_call, PIPE, Popen
from unittest import SkipTest, skipUnless
from yaml import safe_dump

from twisted.internet.defer import gatherResults
from twisted.python.filepath import FilePath
from twisted.python.procutils import which

from flocker.node._docker import DockerClient
from flocker.testtools import loop_until

try:
    from pymongo import MongoClient
    from pymongo.errors import ConnectionFailure
    PYMONGO_INSTALLED = True
except ImportError:
    PYMONGO_INSTALLED = False

__all__ = [
    'assert_expected_deployment', 'flocker_deploy', 'get_nodes',
    'MONGO_APPLICATION', 'MONGO_IMAGE', 'require_flocker_cli',
    ]

# The port on which the acceptance testing nodes make docker available
REMOTE_DOCKER_PORT = 2375

# XXX The MONGO_APPLICATION will have to be removed because it does not match
# the tutorial yml files, and the yml should be testably the same:
# https://github.com/ClusterHQ/flocker/issues/947
MONGO_APPLICATION = u"mongodb-example-application"
MONGO_IMAGE = u"clusterhq/mongodb"

# XXX This assumes that the desired version of flocker-cli has been installed.
# Instead, the testing environment should do this automatically.
# See https://github.com/ClusterHQ/flocker/issues/901.
require_flocker_cli = skipUnless(which("flocker-deploy"),
                                 "flocker-deploy not installed")

require_mongo = skipUnless(
    PYMONGO_INSTALLED, "PyMongo not installed")


def _run_SSH(port, user, node, command, input, key=None):
    """
    Run a command via SSH.

    :param int port: Port to connect to.
    :param bytes user: User to run the command as.
    :param bytes node: Node to run command on.
    :param command: Command to run.
    :type command: ``list`` of ``bytes``.
    :param bytes input: Input to send to command.
    :param FilePath key: If not None, the path to a private key to use.

    :return: stdout as ``bytes``.
    """
    quotedCommand = ' '.join(map(shell_quote, command))
    command = [
        b'ssh',
        b'-p', b'%d' % (port,),
        ]
    if key is not None:
        command.extend([
            b"-i",
            key.path])
    command.extend([
        b'@'.join([user, node]),
        quotedCommand
    ])
    process = Popen(command, stdout=PIPE, stdin=PIPE)

    result = process.communicate(input)
    if process.returncode != 0:
        raise Exception('Command Failed', command, process.returncode)

    return result[0]


def _clean_node(ip):
    """
    Remove all containers and zfs volumes on a node, given the IP address of
    the node. Returns a Deferred which fires when finished.
    """
    docker_client = DockerClient(base_url=u'tcp://' + ip + u':' +
                                 unicode(REMOTE_DOCKER_PORT))
    d = docker_client.list()

    d = d.addCallback(lambda units:
                      gatherResults(
                          [docker_client.remove(unit.name) for unit in units]))

    # Without the below, deploying the same application with a data volume
    # twice fails. See the error given with the tutorial's yml files:
    #
    #   $ flocker-deploy volume-deployment.yml volume-application.yml
    #   $ ssh root@${NODE} docker ps -a -q # outputs an ID, ${ID}
    #   $ ssh root@${NODE} docker stop ${ID}
    #   $ ssh root@${NODE} docker rm ${ID}
    #   $ flocker-deploy volume-deployment.yml volume-application.yml
    #
    # http://doc-dev.clusterhq.com/advanced/cleanup.html#removing-zfs-volumes
    # A tool or flocker-deploy option to purge the state of a node does
    # not yet exist. See https://github.com/ClusterHQ/flocker/issues/682
    d = d.addCallback(
        lambda _: _run_SSH(22, 'root', ip, [b"zfs"] + [b"destroy"] + [b"-r"] +
                           [b"flocker"], None))
    return d


def get_nodes(num_nodes):
    """
    Create ``num_nodes`` nodes with no Docker containers on them.

    This is an alternative to
    http://doc-dev.clusterhq.com/gettingstarted/tutorial/
    vagrant-setup.html#creating-vagrant-vms-needed-for-flocker

    XXX This is a temporary solution which ignores num_nodes and returns the IP
    addresses of the acceptance testing VMs which must already be started.
    num_nodes Docker containers will be created instead to replace this, see
    https://github.com/ClusterHQ/flocker/issues/900

    :param int num_nodes: The number of nodes to start up.
    :return: A ``Deferred`` which fires with a set of IP addresses.
    """
    nodes = set([b"172.16.255.240", b"172.16.255.241"])

    for node in nodes:
        sock = socket()
        sock.settimeout(0.1)
        try:
            can_connect = not sock.connect_ex((node, REMOTE_DOCKER_PORT))
        finally:
            sock.close()

    if not can_connect:
        raise SkipTest("Acceptance testing nodes must be running.")

    d = gatherResults([_clean_node(node) for node in nodes])
    d.addCallback(lambda _: nodes)
    return d


def flocker_deploy(test_case, deployment_config, application_config):
    """
    Run ``flocker-deploy`` with given configuration files.

    :param test_case: The ``TestCase`` running this unit test.
    :param dict deployment_config: The desired deployment configuration.
    :param dict application_config: The desired application configuration.
    """
    temp = FilePath(test_case.mktemp())
    temp.makedirs()

    deployment = temp.child(b"deployment.yml")
    deployment.setContent(safe_dump(deployment_config))

    application = temp.child(b"application.yml")
    application.setContent(safe_dump(application_config))

    check_call([b"flocker-deploy", deployment.path, application.path])


def get_mongo_client(host, port=27017):
    """
    Returns a ``Deferred`` which fires with a ``MongoClient`` when one has been
    created.

    See http://api.mongodb.org/python/current/api/pymongo/mongo_client.html#
        pymongo.mongo_client.MongoClient
    for more parameter information.

    :param bytes host: Hostname or IP address of the instance to connect to.
    :param int port: Port number on which to connect.

    The tutorial says "If you get a connection refused error try again after a
    few seconds; the application might take some time to fully start up."
    and so here we wait until the client can be created.
    """
    def create_mongo_client():
        try:
            return MongoClient(host=host, port=port)
        except ConnectionFailure:
            return False

    d = loop_until(create_mongo_client)
    return d


def assert_expected_deployment(test_case, expected_deployment):
    """
    Assert that the set of units expected on a set of nodes is the same as
    the set of units on those nodes.

    :param test_case: The ``TestCase`` running this unit test.
    :param dict expected_deployment: A mapping of IP addresses to sets of units
        expected on the nodes with those IP addresses.

    :return: A ``Deferred`` which fires with an assertion that the set of units
        on a group of nodes is the same as ``expected_deployment``.
    """
    sorted_nodes = sorted(expected_deployment.keys())

    d = gatherResults(
        [DockerClient(base_url=u'tcp://' + node + u':' +
                      unicode(REMOTE_DOCKER_PORT)).list() for node in
         sorted_nodes])

    # XXX Wait for the unit states to be as expected using wait_for_unit_state
    # github.com/ClusterHQ/flocker/pull/897#discussion_r19024193
    # See https://github.com/ClusterHQ/flocker/issues/937

    d.addCallback(lambda units_sorted_by_node: test_case.assertEqual(
        dict(zip(sorted_nodes, units_sorted_by_node)),
        expected_deployment
    ))

    return d
