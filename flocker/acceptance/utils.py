# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

from json import loads
from pipes import quote as shellQuote
from subprocess import Popen, PIPE
from unittest import skipUnless

from docker import Client

from twisted.python.procutils import which

from flocker.node._docker import NamespacedDockerClient, Unit
from flocker.testtools import random_name

__all__ = [
    # TODO Make things not here private
    'running_units', 'remove_all_containers', 'require_installed',
    ]


def running_units(ip):
    """
    Containers which are running on a node.

    This is a hack and could hopefully use docker py over ssh.
    """
    container_ids = runSSH(22, 'root', ip, [b"docker"] + [b"ps"] + [b"-q"],
                           None).splitlines()

    containers = []
    for container in container_ids:
        inspect = runSSH(22, 'root', ip, [b"docker"] + [b"inspect"] +
                         [container], None)
        details = loads(inspect)[0]

        # TODO use frozenset of PortMap instances from ``details`` for ports
        # and check the activation state.

        unit = Unit(name=details['Name'][1:],
                    container_name=details['Name'][1:],
                    activation_state=u'active',
                    container_image=details['Config']['Image'],
                    ports=(),
                    )
        containers.append(unit)

    return containers


def remove_all_containers(ip):
    """
    Remove all containers on a node
    """
    container_ids = runSSH(22, 'root', ip, [b"docker"] + [b"ps"] + [b"-a"] +
                           [b"-q"], None).splitlines()
    for container in container_ids:
        runSSH(22, 'root', ip, [b"docker"] + [b"rm"] + [b"-f"] + [container],
               None)


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

# TODO Look at
# https://github.com/ClusterHQ/flocker/compare/acceptance-tests-577
# for a start on installing flocker-deploy latest
# The version of flocker-deploy should probably also be checked
require_installed = skipUnless(which("flocker-deploy"),
                               "flocker-deploy not installed")

USE_VAGRANT = True


def get_node_ips():
    """
    Get the IPs of the two nodes to deploy and manage containers on.

    This is an alternative to
    http://doc-dev.clusterhq.com/gettingstarted/tutorial/
    vagrant-setup.html#creating-vagrant-vms-needed-for-flocker

    Unlike the tutorial which uses Vagrant nodes, we want to have docker
    containers, and run docker-in-docker:
      https://blog.docker.com/2013/09/docker-can-now-run-within-docker/

    Until that is viable, we can write the tests to use the Vagrant VMs
    The start of the docker-in-docker plan is below the return
    Start the VMs manually by following the tutorial
    The VMs may not be "clean" so assert that there are no
    containers running.

    The following is a messy way to remove all containers on node_1:
ssh root@172.16.255.250 docker stop $(ssh root@172.16.255.250 docker ps -a -q)
ssh root@172.16.255.250 docker rm $(ssh root@172.16.255.250 docker ps -a -q)

    Use runSSH from HybridCluster to do this automatically?
    """
    if USE_VAGRANT:
        node_1_ip = "172.16.255.250"
        node_2_ip = "172.16.255.251"
        # As a horrid workaround for not having namespacing support
        # in this rudementary client for docker, just remove all the
        # running containers on a node
        remove_all_containers(node_1_ip)
        remove_all_containers(node_2_ip)
        return node_1_ip, node_2_ip

    namespace = u"acceptance-tests"
    client = NamespacedDockerClient(namespace)
    node_1_name = random_name()
    node_2_name = random_name()
    image = u"openshift/busybox-http-app"
    # TODO Enable ssh on the nodes by changing the image
    # also expose the port
    # Also these need dependencies installed, so they will probably be
    # a fedora image with zfs and others
    # Look at using http://www.packer.io to build Vagrant image and Docker
    # image
    d = client.add(node_1_name, image)

    d.addCallback(lambda _: client.add(node_2_name, image))
    d.addCallback(lambda _: client.list())
    # TODO wait_for_unit_state? Why (not)?
    #   from flocker.node.testtools import wait_for_unit_state

    # TODO add cleanup
    #   self.addCleanup(self.client.remove, node_1_name)

    def get_ips(units):
        docker = Client()
        prefix = u'flocker--' + namespace + u'--'

        node_1 = docker.inspect_container(prefix + node_1_name)
        node_2 = docker.inspect_container(prefix + node_2_name)

        node_1_ip = node_1['NetworkSettings']['IPAddress']
        node_2_ip = node_2['NetworkSettings']['IPAddress']
        return node_1_ip, node_2_ip

    d.addCallback(get_ips)
    return d

# TODO Make flocker-deploy a utility function
