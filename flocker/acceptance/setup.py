# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Setup for acceptance testing.

Invoke as "sudo -E $(type -p python) -m flocker.acceptance.setup"
"""
from flocker.node._docker import NamespacedDockerClient
from flocker.node.testtools import wait_for_unit_state

if __name__ == "__main__":
    from flocker.acceptance.setup import setup_docker_containers
    setup_docker_containers()

def setup_docker_containers():
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
    unit_name = "node1"
    image_name=u"openshift/busybox-http-app"
    ports = None
    expected_states = (u'active',)
    environment = None
    volumes = ()
    # Check if acceptance testing containers are already running.
    # If they are then they output that they are running and stop
    # Look at (uses of) NamespacedDockerClient
