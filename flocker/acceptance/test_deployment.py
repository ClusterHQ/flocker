# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for deploying applications.

You need flocker-deploy installed
Run with:

  $ sudo -E PATH=$PATH $(type -p trial) --temp=/tmp/trial flocker.acceptance
"""
from subprocess import check_output
from unittest import skipUnless

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
        """
        namespace = u"acceptance-tests"
        self.client = NamespacedDockerClient(namespace)
        self.node_1_name = random_name()
        self.node_2_name = random_name()

        d = self.client.add(self.node_1_name, u"openshift/busybox-http-app")
        d = self.client.add(self.node_2_name, u"openshift/busybox-http-app")
        # wait_for_unit_state?
        # add cleanup
        return d

    def test_deploy(self):
        """
        Call a 'deploy' utility function with an application and deployment
        config and watch docker ps output.
        """
        # TODO Write out YAML files or use ready-made ones?
        # minimal-application.yml as made for the documentation is suitable
        # but minimal-deployment.yml needs to know node IP addresses
        # Is it possible to set the docker container's IP addresses? If not,
        # is it possible to find them?
        # How do we specify that the containers should be priviledged (so as
        # to be able to be run inside )
        # TODO no need to check output, just run the command
        check_output([b"flocker-deploy"] + [b"application.yml"] +
                     [b"deployment.yml"])
        # TODO use self.client.list() to check that the application is
        # deployed onto the right node
