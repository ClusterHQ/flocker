# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Setup for acceptance testing.
"""
from twisted.trial.unittest import TestCase
from flocker.node._docker import NamespacedDockerClient
from flocker.node.testtools import wait_for_unit_state
from flocker.testtools import random_name


class ExampleTests(TestCase):
    """
    Playground for trying out acceptance test ideas.
    """
    
    def test_setup_docker_containers(self):
        """
        Set up docker containers for acceptance testing.

        These are identifiable as the acceptance testing containers so that they
        can later be removed without affecting other Docker containers.

        This is an alternative to
        http://doc-dev.clusterhq.com/gettingstarted/tutorial/vagrant-setup.html#creating-vagrant-vms-needed-for-flocker

        Whether to do this at the beginning of each test or the beginning of the
        test suite depends partially on how long it takes.
        """
        namespace = u"acceptance-tests"
        client = NamespacedDockerClient(namespace)
        node_1_name = random_name()
        node_2_name = random_name()

        d = client.add(node_1_name, u"openshift/busybox-http-app")
        d = client.add(node_2_name, u"openshift/busybox-http-app")
        # wait_for_unit_state?
        # add cleanup
        return d
        # Check if acceptance testing containers are already running.
        # If they are then they output that they are running and stop
        # Look at (uses of) NamespacedDockerClient
