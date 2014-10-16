# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for moving applications between nodes.
"""
from yaml import safe_dump

from twisted.internet.defer import gatherResults
from twisted.python.filepath import FilePath
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

            temp = FilePath(self.mktemp())
            temp.makedirs()

            application_config = temp.child(b"application.yml")
            application_config.setContent(safe_dump({
                u"version": 1,
                u"applications": {
                    u"mongodb-example": {
                        u"image": u"clusterhq/mongodb",
                    },
                },
            }))

            deployment_config = temp.child(b"deployment.yml")
            deployment_config.setContent(safe_dump({
                u"version": 1,
                u"nodes": {
                    node_1: [u"mongodb-example"],
                    node_2: [],
                },
            }))

            flocker_deploy(deployment_config, application_config)

            # TODO change this and other yml names to match the tutorial
            deployment_moved_config = temp.child(b"deployment.yml")
            deployment_moved_config.setContent(safe_dump({
                u"version": 1,
                u"nodes": {
                    node_1: [],
                    node_2: [u"mongodb-example"],
                },
            }))

            flocker_deploy(deployment_moved_config, application_config)

            unit = Unit(name=u'mongodb-example',
                        container_name=BASE_NAMESPACE + u'mongodb-example',
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
