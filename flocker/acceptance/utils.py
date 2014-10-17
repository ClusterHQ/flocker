# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

from pipes import quote as shellQuote
from subprocess import call, PIPE, Popen
from unittest import skipUnless

from twisted.internet.defer import gatherResults
from twisted.python.procutils import which

from flocker.node._docker import RemoteDockerClient

__all__ = [
    'flocker_deploy', 'get_nodes', 'require_flocker_cli', 'require_mongo',
    ]


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


def runSSH(port, user, node, command, input, key=None):
    """
    XXX This is taken directly from HybridCluster and is perhaps not all
    necessary. It is also not formatted like flocker code.

    Run a command via SSH.

    @param port: Port to connect to.
    @type port: L{int}
    @param node: Node to run command on
    @param node: L{bytes}
    @param command: command to run
    @type command: L{list} of L{bytes}
    @param input: Input to send to command.
    @type input: L{bytes}

    @param key: If not L{None}, the path to a private key to use.
    @type key: L{FilePath}

    @return: stdout
    @rtype: L{bytes}
    """
    quotedCommand = ' '.join(map(shellQuote, command))
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
    docker_client = RemoteDockerClient(ip)
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
    d = d.addCallback(lambda _:
                      runSSH(22, 'root', ip,
                             [b"zfs"] + [b"destroy"] + [b"-r"] + [b"flocker"],
                             None))
    return d


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
    Should I remove the parameter? It isn't used but I want the tests to be
    written in such a way that they don't have to change when Docker-in-Docker
    arrives.

    :param int num_nodes: The number of nodes to start up.
    :return: A a deferred which fires with a list of IP addresses.
    """
    nodes = [b"172.16.255.250", b"172.16.255.251"]
    # The problem with this is that anyone running "trial flocker" while
    # their tutorial nodes are running may inadvertently remove all
    # containers which are running on those nodes. If it stays this way
    # I'll leave it to a reviewer to decide if that is so bad that it must
    # be changed (note that in future this will be dropped for a
    # Docker-in-Docker solution).

    # XXX Ping the nodes and give a sensible error if they aren't available?
    d = gatherResults([_clean_node(node) for node in nodes])
    d.addCallback(lambda _: nodes)
    return d


def flocker_deploy(deployment, application):
    """
    Run ``flocker-deploy`` with given configuration files.

    :param FilePath deployment: A YAML file describing the desired deployment
        configuration.
    :param FilePath application: A YAML file describing the desired application
        configuration.
    """
    call([b"flocker-deploy"] + [deployment.path] + [application.path])
