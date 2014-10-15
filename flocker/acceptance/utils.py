# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

from json import loads
from pipes import quote as shellQuote
from subprocess import check_output, Popen, PIPE
from time import sleep
from unittest import skipUnless

from docker import Client

from twisted.python.procutils import which

from flocker.node._docker import DockerClient, NamespacedDockerClient, Unit
from flocker.testtools import random_name

# TODO link from the documentation to the tests
# TODO try to use docker client - modify the vagrant image to allow it
# TODO document how someone would use this
# TODO split out the vagrant stuff from the docker stuff
# TODO create issues for follow up - ELK/PostgreSQL, Docker-in-Docker
# TODO if num_nodes is not 2, raise an exception
# TODO run coverage

__all__ = [
    'running_units', 'remove_all_containers', 'require_installed',
    ]


def running_units(ip):
    """
    Containers which are running on a node.

    Note: This is a hack and, like running_units, should use (something closer
    to) DockerClient. In fact most of this code is copied from
    ``DockerClient.list``.
    """
    docker = DockerClient()
    container_ids = runSSH(22, 'root', ip, [b"docker"] + [b"ps"] + [b"-q"],
                           None).splitlines()

    result = set()
    for container in container_ids:
        inspect = runSSH(22, 'root', ip, [b"docker"] + [b"inspect"] +
                         [container], None)

        data = loads(inspect)[0]
        state = (u"active" if data[u"State"][u"Running"]
                 else u"inactive")
        name = data[u"Name"]
        image = data[u"Config"][u"Image"]
        port_mappings = data[u"NetworkSettings"][u"Ports"]
        if port_mappings is not None:
            ports = docker._parse_container_ports(port_mappings)
        else:
            ports = list()

        # XXX to extract volume info from the inspect results:
        # https://github.com/ClusterHQ/flocker/issues/289
        result.add(Unit(name=name,
                        container_name=name,
                        activation_state=state,
                        container_image=image,
                        ports=frozenset(ports)))

    return result


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
            # TODO I sometimes see:
            # Error response from daemon: Cannot destroy container
            # 08f9ca89053c: Driver devicemapper failed to remove root
            # filesystem
            # 08f9ca89053c782130e7394caacc03a00cf9b621e251f909897a9f0c30dfdc72:
            # Device is Busy
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

# TODO Look at
# https://github.com/ClusterHQ/flocker/compare/acceptance-tests-577
# for a start on installing flocker-deploy latest
# The version of flocker-deploy should probably also be checked
require_installed = skipUnless(which("flocker-deploy"),
                               "flocker-deploy not installed")

USE_VAGRANT = True


def get_nodes(num_nodes):
    """
    Create ``num_nodes`` nodes with no Docker containers on them.

    This is an alternative to
    http://doc-dev.clusterhq.com/gettingstarted/tutorial/
    vagrant-setup.html#creating-vagrant-vms-needed-for-flocker

    Unlike the tutorial which uses Vagrant nodes, we want to have Docker
    containers, and run Docker-in-Docker:
      https://blog.docker.com/2013/09/docker-can-now-run-within-docker/

    Until that is viable, we can write the tests to use the Vagrant VMs
    The start of the Docker-in-Docker plan is below the return.

    Follow the Release Process's review process to get up to date VMs running,
    or the tutorial for the latest release.

    :param int num_nodes: The number of nodes to start up.
    :return: A ``list`` of ``bytes``, the IP addresses of the nodes created.
    """
    if USE_VAGRANT:
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

    namespace = u"acceptance-tests"
    client = NamespacedDockerClient(namespace)
    # TODO use num_nodes instead of just 2 nodes
    node_1_name = random_name()
    node_2_name = random_name()
    image = u"openshift/busybox-http-app"
    # TODO Enable ssh on the nodes by changing the images
    # Look at using http://www.packer.io to build Vagrant image and Docker
    # image so that we have all the dependencies
    d = client.add(node_1_name, image)

    d.addCallback(lambda _: client.add(node_2_name, image))
    d.addCallback(lambda _: client.list())
    # TODO wait_for_unit_state - we want active units
    #   from flocker.node.testtools import wait_for_unit_state

    # TODO add cleanup
    #   self.addCleanup(self.client.remove, node_1_name)

    # How do we specify that the containers should be priviledged (so as
    # to be able to be run inside another docker container)

    def get_ips(units):
        docker = Client()
        prefix = u'flocker--' + namespace + u'--'

        node_1 = docker.inspect_container(prefix + node_1_name)
        node_2 = docker.inspect_container(prefix + node_2_name)

        node_1_ip = node_1['NetworkSettings']['IPAddress']
        node_2_ip = node_2['NetworkSettings']['IPAddress']
        # Is this always bytes?
        return [node_1_ip, node_2_ip]

    d.addCallback(get_ips)
    return d


def flocker_deploy(deployment_config, application_config):
    """
    Run ``flocker-deploy`` with given configuration files.

    :param FilePath deployment_config: A YAML file describing the desired
        deployment configuration.
    :param FilePath application_config: A YAML file describing the desired
        application configuration.
    """
    check_output([b"flocker-deploy"] +
                 [deployment_config.path] +
                 [application_config.path])
    # TODO Use something like wait_for_active instead of this
    sleep(2)
