# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

from subprocess import check_output
from time import sleep
from unittest import skipUnless

from twisted.internet.defer import gatherResults
from twisted.python.procutils import which

from flocker.node._docker import RemoteDockerClient

# TODO link from the documentation to the tests
# TODO run coverage

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


def _remove_all_containers(ip):
    """
    Remove all containers on a node, given the IP address of the node. Returns
    a Deferred which fires when all containers have been removed.
    """
    docker_client = RemoteDockerClient(ip)
    d = docker_client.list()

    d.addCallback(lambda units:
                  gatherResults(
                      [docker_client.remove(unit.name) for unit in units]))

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
    d = gatherResults([_remove_all_containers(node) for node in nodes])
    d.addCallback(lambda _: nodes)
    return d


def flocker_deploy(deployment_config, application_config):
    """
    Run ``flocker-deploy`` with given configuration files.

    :param FilePath deployment_config: A YAML file describing the desired
        deployment configuration.
    :param FilePath application_config: A YAML file describing the desired
        application configuration.
    """
    # TODO check_output - not necessary, just wait for it to finish
    check_output([b"flocker-deploy"] + [deployment_config.path] +
                 [application_config.path])
    # XXX Without this some of the tests fail, so there is a race condition.
    # My guess is that this is because `flocker-deploy` returns too
    # early. The issue that describes similar behaviour is
    # https://github.com/ClusterHQ/flocker/issues/341
    # XXX Check if this is `mongo` taking its time to start up - if so add
    # the sleep there. The tutorial says of mongo "If you get a connection
    # refused error try again after a few seconds; the application might take
    # some time to fully start up.".
    sleep(2)
