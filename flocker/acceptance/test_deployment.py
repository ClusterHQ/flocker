# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for deploying applications.

You need flocker-deploy installed
Run with:

  $ sudo -E PATH=$PATH $(type -p trial) --temp=/tmp/trial flocker.acceptance
"""
from subprocess import check_output
from unittest import skipUnless

from docker import Client

from twisted.python.procutils import which
from twisted.trial.unittest import TestCase

from flocker.node._docker import NamespacedDockerClient
#from flocker.node.testtools import wait_for_unit_state
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
        namespace = u"acceptance-tests"
        self.client = NamespacedDockerClient(namespace)
        node_1_name = random_name()
        node_2_name = random_name()
        image = u"openshift/busybox-http-app"
        d = self.client.add(node_1_name, image)

        d.addCallback(lambda _: self.client.add(node_2_name, image))
        d.addCallback(lambda _: self.client.list())
        # TODO wait_for_unit_state? Why (not)?
        # add cleanup

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
        # TODO Write out YAML files or use ready-made ones?
        # minimal-application.yml as made for the documentation is suitable
        # but minimal-deployment.yml needs to know node IP addresses
        # Is it possible to set the docker container's IP addresses? Instead
        # of just finding them
        # How do we specify that the containers should be priviledged (so as
        # to be able to be run inside)
        # TODO no need to check output, just run the command
        import pdb; pdb.set_trace()
        check_output([b"flocker-deploy"] + [b"application.yml"] +
                     [b"deployment.yml"])
        # TODO use self.client.list() to check that the application is
        # deployed onto the right node
