# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for deploying applications.

You need flocker-deploy installed
Run with:

  $ sudo -E PATH=$PATH $(type -p trial) --temp=/tmp/trial flocker.acceptance.test_deployment
"""

from twisted.trial.unittest import TestCase
from flocker.node._docker import NamespacedDockerClient
from flocker.node.testtools import wait_for_unit_state
from flocker.testtools import random_name

from subprocess import check_output

_require_installed = skipUnless(which("flocker-deploy"),
                                "flocker-deploy not installed")

class DeploymentTests(TestCase):
    """
    Tests for deploying applications.

    Similar to http://doc-dev.clusterhq.com/gettingstarted/tutorial/moving-applications.html#starting-an-application
    """
    @_require_installed
    def setUp(self):
        """
        This is an alternative to
        http://doc-dev.clusterhq.com/gettingstarted/tutorial/vagrant-setup.html#creating-vagrant-vms-needed-for-flocker
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
        result = check_output([b"flocker-deploy"] + [b"utils.py"] + [b"utils2.py"])
        self.assertEqual(result, b"%s\n" % (5,))
