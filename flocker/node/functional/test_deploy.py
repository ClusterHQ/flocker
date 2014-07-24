# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Functional tests for ``flocker.node._deploy``.
"""

from subprocess import check_call

from twisted.trial.unittest import TestCase

from .. import Deployer, Deployment, Application, DockerImage, Node
from ..gear import GearClient
from ..testtools import wait_for_unit_state, if_gear_configured
from ...testtools import create_volume_service, random_name
from ...route import make_memory_network


class DeployerTests(TestCase):
    """
    Functional tests for ``Deployer``.
    """
    @if_gear_configured
    def test_restart(self):
        """
        Stopped applications that are supposed to be running are restarted
        when ``Deployer.change_node_state`` is run.
        """
        name = random_name()
        gear_client = GearClient("127.0.0.1")
        deployer = Deployer(create_volume_service(self), gear_client,
                            make_memory_network())
        self.addCleanup(gear_client.remove, name)

        desired_state = Deployment(nodes=frozenset([
            Node(hostname=u"localhost",
                 applications=frozenset([Application(
                     name=name,
                     image=DockerImage.from_string(
                         u"openshift/busybox-http-app"))]))]))

        d = deployer.change_node_state(desired_state, u"localhost")
        d.addCallback(lambda _: wait_for_unit_state(gear_client, name,
                                                    [u'active']))

        def started(_):
            # Now that it's running, stop it behind our back:
            check_call([b"gear", b"stop", name])
            return wait_for_unit_state(gear_client, name, u'inactive')
        d.addCallback(started)

        def stopped(_):
            # Redeploy, which should restart it:
            return deployer.change_node_state(desired_state, u"localhost")
        d.addCallback(stopped)
        d.addCallback(lambda _: wait_for_unit_state(gear_client, name,
                                                    [u'active']))

        # Test will timeout if unit was not restarted:
        return d
