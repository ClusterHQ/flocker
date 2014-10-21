# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

from pipes import quote as shell_quote
from subprocess import call, PIPE, Popen
from unittest import skipUnless
from yaml import safe_dump

from twisted.internet.defer import gatherResults
from twisted.python.filepath import FilePath
from twisted.python.procutils import which

from flocker.node._docker import DockerClient

__all__ = [
    'flocker_deploy', 'get_nodes', 'require_flocker_cli',
    'require_mongo', 'create_remote_docker_client'
    ]

# TODO have a wait_until method and call it from any test which needs an
# active container github.com/ClusterHQ/flocker/pull/897#discussion_r19024193

# TODO Document how to build the vagrant tutorial / testing box

# TODO https://github.com/ClusterHQ/flocker/pull/897#issuecomment-59541962
# Think about how to expose fewer implementation details in the tests

# TODO Think about coverage - should it skip the whole module?
# https://github.com/ClusterHQ/flocker/pull/897#discussion_r19010139

# XXX This assumes that the desired version of flocker-cli has been installed.
# Instead, the testing environment should do this automatically.
# See https://github.com/ClusterHQ/flocker/issues/901.
require_flocker_cli = skipUnless(which("flocker-deploy"),
                                 "flocker-deploy not installed")

# XXX This assumes that the desired version of mongo has been installed.
# Instead, the testing environment should do this automatically.
# See https://github.com/ClusterHQ/flocker/issues/901.
require_mongo = skipUnless(which("mongo"),
                           "The mongo shell is not available.")


def _run_SSH(port, user, node, command, input, key=None):
    """
    Run a command via SSH.

    :param int port: Port to connect to.
    :param bytes node: Node to run command on
    :param command: Command to run
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
    docker_client = DockerClient(base_url=u'tcp://' + ip + u':2375')
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
    d = d.addCallback(lambda _:
                      _run_SSH(22, 'root', ip,
                               [b"zfs"] + [b"destroy"] + [b"-r"] +
                               [b"flocker"], None))
    return d


def create_remote_docker_client(ip, port):
    """
    Create and return a ``DockerClient`` using a TCP connection string
    as the base URL.

    :param str ip: The IP address or hostname of the target Docker API.

    :param int port: The port number to connect on.

    :returns: A ``DockerClient`` instance.
    """
    base_url = ''.join(['tcp://', ip, ':', str(port)])
    return DockerClient(base_url=base_url)


def get_nodes(num_nodes):
    """
    Create ``num_nodes`` nodes with no Docker containers on them.

    This is an alternative to
    http://doc-dev.clusterhq.com/gettingstarted/tutorial/
    vagrant-setup.html#creating-vagrant-vms-needed-for-flocker

    XXX This is a temporary solution which ignores num_nodes and returns the IP
    addresses of the tutorial VMs which must already be started. num_nodes
    Docker containers will be created instead to replace this, see
    https://github.com/ClusterHQ/flocker/issues/900

    :param int num_nodes: The number of nodes to start up.
    :return: A ``Deferred`` which fires with a set of IP addresses.
    """
    nodes = set([b"172.16.255.250", b"172.16.255.251"])
    # The problem with this is that anyone running "trial flocker" while
    # their tutorial nodes are running may inadvertently remove all
    # containers which are running on those nodes.
    # TODO Temporarily require an environment variable to be set
    # github.com/ClusterHQ/flocker/pull/897#discussion_r19024847

    # XXX Ping the nodes and give a sensible error if they aren't available?
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
    # TODO move requirement for flocker-deploy here, if possible

    temp = FilePath(test_case.mktemp())
    temp.makedirs()

    deployment = temp.child(b"deployment.yml")
    deployment.setContent(safe_dump(deployment_config))

    application = temp.child(b"application.yml")
    application.setContent(safe_dump(application_config))

    call([b"flocker-deploy"] + [deployment.path] + [application.path])


# TODO make this public
# TODO can we remove remote docker client / put it in here / private?
def assertExpectedDeployment(test_case, expected):
    """
    :param test_case: The ``TestCase`` running this unit test.

    # TODO better docstring

    Expected: A dictionary mapping IP addresses to their expected deployments
    e.g.
    {
        node1: set([some_unit]),
        node2: set([])
    }
    """
    actual = {}
    deferreds = []
    sorted_nodes = sorted(expected.keys())
    for node in sorted_nodes:
        client = DockerClient(base_url=u'tcp://' + node + u':2375')
        deferreds.append(client.list())

    def add_units(units):
        """
        units is a list of sets of all units on the expected nodes, sorted
        by the IP address of the corresponding node.
        """
        for node in reversed(sorted_nodes):
            actual[node] = units.pop()
        test_case.assertEqual(actual, expected)

    d = gatherResults(deferreds)
    d.addCallback(add_units)
