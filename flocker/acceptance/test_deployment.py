# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for deploying applications.

You need flocker-deploy installed
Run with:

  $ sudo -E PATH=$PATH $(type -p trial) --temp=/tmp/trial flocker.acceptance
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

_require_installed = skipUnless(which("flocker-deploy"),
                                "flocker-deploy not installed")


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
        node_1_ip = "172.16.255.250"
        node_2_ip = "172.16.255.251"
        deployment_config_path = temp.child(b"deployment.yml")
        deployment_config_path.setContent(safe_dump({
            u"version": 1,
            u"nodes": {
                node_1_ip: [u"mongodb-example"],
                node_2_ip: [],
            },
        }))
        result = check_output([b"flocker-deploy"] +
            [deployment_config_path.path] + [application_config_path.path])

        # We now want to check that the application is deployed. We could
        # do this with runSSH and then checking the output with regex OR
        # I'd hope that it isn't too hard to use docker-py over SSH.
