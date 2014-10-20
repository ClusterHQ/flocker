# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for moving applications between nodes.
"""
from twisted.internet.defer import gatherResults
from twisted.trial.unittest import TestCase

from flocker.node._docker import BASE_NAMESPACE, RemoteDockerClient, Unit

from .utils import flocker_deploy, get_nodes, require_flocker_cli


class MovingApplicationTests(TestCase):
    """
    Tests for moving applications between nodes.

    Similar to http://doc-dev.clusterhq.com/gettingstarted/tutorial/
    moving-applications.html#moving-an-application
    """
    @require_flocker_cli
    def setUp(self):
        pass

    def test_moving_application(self):
        """
        After deploying an application to one node and then moving it onto
        another node, it is only on the second node.
        """
        d = get_nodes(num_nodes=2)

        def deploy_and_move(node_ips):
            node_1, node_2 = node_ips

            application = u"mongodb-example"

            application_config = {
                u"version": 1,
                u"applications": {
                    application: {
                        u"image": u"clusterhq/mongodb",
                    },
                },
            }

            deployment_config = {
                u"version": 1,
                u"nodes": {
                    node_1: [application],
                    node_2: [],
                },
            }

            flocker_deploy(self, deployment_config, application_config)

            deployment_moved_config = {
                u"version": 1,
                u"nodes": {
                    node_1: [],
                    node_2: [application],
                },
            }

            flocker_deploy(self, deployment_moved_config, application_config)

            unit = Unit(name=application,
                        container_name=BASE_NAMESPACE + application,
                        activation_state=u'active',
                        container_image=u'clusterhq/mongodb:latest',
                        ports=frozenset(), environment=None, volumes=())

            d = gatherResults([RemoteDockerClient(node_1).list(),
                               RemoteDockerClient(node_2).list()])

            def listed(units):
                node_1_list, node_2_list = units
                self.assertEqual([set(), set([unit])],
                                 [node_1_list, node_2_list])

            d.addCallback(listed)
            return d

        d.addCallback(deploy_and_move)
        return d
