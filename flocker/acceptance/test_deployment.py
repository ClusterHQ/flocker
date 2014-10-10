# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for deploying applications.

You need flocker-deploy installed
Run with:

  $ sudo -E PATH=$PATH $(type -p trial) --temp=/tmp/trial flocker.acceptance

for the docker-in-docker stuff, else trial flocker.acceptance is fine
"""
from subprocess import check_output
from unittest import skipUnless
from yaml import safe_dump

from docker import Client

from twisted.python.procutils import which
from twisted.python.filepath import FilePath
from twisted.trial.unittest import TestCase

from flocker.node._docker import NamespacedDockerClient

from flocker.testtools import random_name

# TODO Look at
# https://github.com/ClusterHQ/flocker/compare/acceptance-tests-577
# for a start on installing flocker-deploy latest
_require_installed = skipUnless(which("flocker-deploy"),
                                "flocker-deploy not installed")


def containers_running(ip):
    """
    Find the number of containers which are running. This is a bit of a hack
    and could hopefully use docker py.
    """
    docker_ps = check_output([b"ssh"] + [b"root@" + ip] + [b"docker"] +
        [b"ps"])
    if docker_ps.startswith('CONTAINER ID'):
        containers = []
        for container in docker_ps.splitlines()[1:]:
            container_id, image, command, created, status, ports, names = (
                [section.strip() for section in container.split('  ') if
                 section.strip() != ''])
            containers.append({'container_id': container_id, 'image': image,
                'command': command, 'created': created, 'status': status,
                'ports': ports, 'names': names})

        return containers
    else:
        # The header is not correct, so it isn't the expected docker_ps
        # outcome
        raise Exception

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
        """
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
        # from flocker.node.testtools import wait_for_unit_state

        # TODO add cleanup
        #     self.addCleanup(self.client.remove, node_1_name)

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
        # Is it possible to set the docker container's IP addresses? Instead
        # of just finding them
        # How do we specify that the containers should be priviledged (so as
        # to be able to be run inside another docker container)

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

        #node_1_ip = self.node_1_ip
        #node_2_ip = self.node_2_ip
        # Use VMs for testing, until the docker container situation is
        # viable
        # The VMs may not be "clean" so assert that there are no
        # containers running.
        # The following is a messy way to remove all containers on node_1:
        # ssh root@172.16.255.250 docker stop $(ssh root@172.16.255.250 docker ps -a -q)
        # ssh root@172.16.255.250 docker rm $(ssh root@172.16.255.250 docker ps -a -q)
        node_1_ip = "172.16.255.250"
        node_2_ip = "172.16.255.251"
        self.assertEqual(len(containers_running(node_1_ip)), 0)
        deployment_config_path = temp.child(b"deployment.yml")
        deployment_config_path.setContent(safe_dump({
            u"version": 1,
            u"nodes": {
                node_1_ip: [u"mongodb-example"],
                node_2_ip: [],
            },
        }))

        check_output([b"flocker-deploy"] +
            [deployment_config_path.path] + [application_config_path.path])

        self.assertEqual(len(containers_running(node_1_ip)), 1)
        # We now want to check that the application is deployed. We could
        # do this with runSSH and then checking the output with regex OR
        # I'd hope that it isn't too hard to use docker-py over SSH.
