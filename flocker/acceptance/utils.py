# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

from json import loads
from pipes import quote as shellQuote
from subprocess import check_output, PIPE, Popen
from time import sleep
from unittest import skipUnless

from twisted.python.procutils import which

from flocker.node._docker import DockerClient, Unit

# TODO link from the documentation to the tests
# TODO try to use docker client
# TODO run coverage
# TODO Search for TODOs

__all__ = [
    'remove_all_containers', 'require_flocker_cli', 'require_mongo',
    ]

def remove_all_containers(ip):
    """
    Remove all containers on a node, given the ip of the node.
    Note: This is a hack and, like running_units, should use (something closer
    to) DockerClient.
    """
    container_ids = runSSH(22, 'root', ip, [b"docker"] + [b"ps"] + [b"-a"] +
                           [b"-q"], None).splitlines()
    for container in container_ids:
        try:
            runSSH(22, 'root', ip, [b"docker"] + [b"rm"] + [b"-f"] +
                   [container], None)
        except Exception:
            # I sometimes see:
            # Error response from daemon: Cannot destroy container
            # 08f9ca89053c: Driver devicemapper failed to remove root
            # filesystem
            # 08f9ca89053c782130e7394caacc03a00cf9b621e251f909897a9f0c30dfdc72:
            # Device is Busy
            #
            # Hopefully replacing this with a Docker py client will avoid
            # this issue.
            pass


def runSSH(port, user, node, command, input, key=None):
    """
    # TODO Format this with a PEP8 style

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
    :return: A ``list`` of ``bytes``, the IP addresses of the nodes created.
    """
    node_1 = b"172.16.255.250"
    node_2 = b"172.16.255.251"
    # The problem with this is that anyone running "trial flocker" while
    # their tutorial nodes are running may inadvertently remove all
    # containers which are running on those nodes. If it stays this way
    # I'll leave it to a reviewer to decide if that is so bad that it must
    # be changed (note that in future this will be dropped for a
    # Docker-in-Docker solution).
    remove_all_containers(node_1)
    remove_all_containers(node_2)
    return [node_1, node_2]


def flocker_deploy(deployment_config, application_config):
    """
    Run ``flocker-deploy`` with given configuration files.

    :param FilePath deployment_config: A YAML file describing the desired
        deployment configuration.
    :param FilePath application_config: A YAML file describing the desired
        application configuration.
    """
    # TODO check_output - check that there is no output
    check_output([b"flocker-deploy"] + [deployment_config.path] +
                 [application_config.path])
    # XXX Without this some of the tests fail, so there is a race condition.
    # My guess is that this is because `flocker-deploy` returns too
    # early. The issue that describes similar behaviour is
    # https://github.com/ClusterHQ/flocker/issues/341
    sleep(2)
