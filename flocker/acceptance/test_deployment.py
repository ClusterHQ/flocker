# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for deploying applications.

You need flocker-deploy installed
Run with:

  $ sudo -E PATH=$PATH $(type -p trial) --temp=/tmp/trial flocker.acceptance

for the docker-in-docker stuff, else trial flocker.acceptance is fine
"""
from pipes import quote as shellQuote
from subprocess import check_output, Popen, PIPE
from unittest import skipUnless
from yaml import safe_dump

from docker import Client

from twisted.python.procutils import which
from twisted.python.filepath import FilePath
from twisted.trial.unittest import TestCase

from flocker.node._docker import NamespacedDockerClient, Unit

from flocker.testtools import random_name

# TODO Look at
# https://github.com/ClusterHQ/flocker/compare/acceptance-tests-577
# for a start on installing flocker-deploy latest
# The version of flocker-deploy should probably also be checked
_require_installed = skipUnless(which("flocker-deploy"),
                                "flocker-deploy not installed")


def containers_running(ip):
    """
    Containers which are running on a node.

    This is a hack and could hopefully use docker py.
    This would be *much* better with namespacing,
    which is hopefully doable with NamespacedDockerClient if that can be used
    over SSH.
    """
    # Use runSSH
    docker_ps = check_output([b"ssh"] + [b"root@" + ip] + [b"docker"] +
                             [b"ps"])
    if docker_ps.startswith('CONTAINER ID'):
        containers = []
        for container in docker_ps.splitlines()[1:]:
            container_id, image, command, created, status, ports, names = (
                [section.strip() for section in container.split('  ') if
                 section.strip() != ''])

            if status.startswith('Up'):
                state = u'active'
            else:
                state = u'inactive'

            # TODO use frozenset of PortMap instances
            ports = ()

            # TODO is the name right?
            unit = Unit(name=names,
                        container_name=names,
                        activation_state=state,
                        container_image=image,
                        ports=ports,
                        )
            containers.append(unit)

        return containers
    else:
        # The header is not correct, so it isn't the expected docker_ps
        # outcome
        raise Exception


def runSSH(port, user, node, command, input, key=None):
    """
    # TODO This should be in utils and be formatted with a PEP8 style

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


def remove_all_containers(ip):
    """
    Remove all containers on a node
    """
    all_containers = runSSH(22, 'root', ip, [b"docker"] + [b"ps"] + [b"-a"] + [b"-q"], None)
    for container in all_containers.splitlines():
        try:
            runSSH(22, 'root', ip, [b"docker"] + [b"stop"] + [container], None)
            runSSH(22, 'root', ip, [b"docker"] + [b"rm"] + [container], None)
        except:
            pass

class DeploymentTests(TestCase):
    """
    Tests for deploying applications.

    Similar to http://doc-dev.clusterhq.com/gettingstarted/tutorial/
    moving-applications.html#starting-an-application
    """
    @_require_installed
    def setUp(self):
        """
        This is an alternative to
        http://doc-dev.clusterhq.com/gettingstarted/tutorial/
        vagrant-setup.html#creating-vagrant-vms-needed-for-flocker

        This will probably be a utility function

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

        vagrant = True
        if vagrant:
            self.node_1_ip = "172.16.255.250"
            self.node_2_ip = "172.16.255.251"
            # TODO As a horrid workaround for not having namespacing support
            # in this rudementary client for docker, just remove all the
            # running containers on a node
            remove_all_containers(self.node_1_ip)
            remove_all_containers(self.node_2_ip)
            return

        namespace = u"acceptance-tests"
        self.client = NamespacedDockerClient(namespace)
        node_1_name = random_name()
        node_2_name = random_name()
        image = u"openshift/busybox-http-app"
        # TODO Enable ssh on the nodes by changing the image
        # also expose the port
        # Also these need dependencies installed, so they will probably be
        # a fedora image with zfs and others
        # Look at using http://www.packer.io to build Vagrant image and Docker
        # image
        d = self.client.add(node_1_name, image)

        d.addCallback(lambda _: self.client.add(node_2_name, image))
        d.addCallback(lambda _: self.client.list())
        # TODO wait_for_unit_state? Why (not)?
        #   from flocker.node.testtools import wait_for_unit_state

        # TODO add cleanup
        #   self.addCleanup(self.client.remove, node_1_name)

        def get_ips(units):
            docker = Client()
            prefix = u'flocker--' + namespace + u'--'

            node_1 = docker.inspect_container(prefix + node_1_name)
            node_2 = docker.inspect_container(prefix + node_2_name)

            self.node_1_ip = node_1['NetworkSettings']['IPAddress']
            self.node_2_ip = node_2['NetworkSettings']['IPAddress']

        d.addCallback(get_ips)
        return d

    def test_deploy(self):
        """
        Call a 'deploy' utility function with an application and deployment
        config and watch docker ps output.
        """
        temp = FilePath(self.mktemp())
        temp.makedirs()

        application_config_path = temp.child(b"application.yml")
        application_config_path.setContent(safe_dump({
            u"version": 1,
            u"applications": {
                u"mongodb-example": {
                    u"image": u"clusterhq/mongodb",
                },
            },
        }))

        containers_running_before = containers_running(self.node_1_ip)
        deployment_config_path = temp.child(b"deployment.yml")
        deployment_config_path.setContent(safe_dump({
            u"version": 1,
            u"nodes": {
                self.node_1_ip: [u"mongodb-example"],
                self.node_2_ip: [],
            },
        }))

        # How do we specify that the containers should be priviledged (so as
        # to be able to be run inside another docker container)
        check_output([b"flocker-deploy"] +
                     [deployment_config_path.path] +
                     [application_config_path.path])

        containers_running_after = containers_running(self.node_1_ip)

        new_containers = (set(containers_running_after) -
                          set(containers_running_before))

        expected = set([Unit(name=u'mongodb-example-data',
                             container_name=u'mongodb-example-data',
                             activation_state=u'active',
                             container_image=u'clusterhq/mongodb:latest',
                             ports=(), environment=None, volumes=())])

        self.assertEqual(new_containers, expected)
