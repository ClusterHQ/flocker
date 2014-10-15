# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for deploying applications.
"""
from yaml import safe_dump

from twisted.internet.defer import gatherResults
from twisted.python.filepath import FilePath
from twisted.trial.unittest import TestCase

from flocker.node._docker import RemoteDockerClient, Unit

from .utils import flocker_deploy, get_nodes, require_flocker_cli


class DeploymentTests(TestCase):
    """
    Tests for deploying applications.

    Similar to:
    http://doc-dev.clusterhq.com/gettingstarted/tutorial/
    moving-applications.html#starting-an-application
    """
    @require_flocker_cli
    def setUp(self):
        pass

    def test_deploy(self):
        """
        Deploying an application to one node and not another puts the
        application where expected.
        """
        temp = FilePath(self.mktemp())
        temp.makedirs()

        d = get_nodes(num_nodes=2)

        def deploy(node_ips):
            node_1, node_2 = node_ips
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

            unit = Unit(name=u'mongodb-example',
                        container_name=u'flocker--mongodb-example',
                        activation_state=u'active',
                        container_image=u'clusterhq/mongodb:latest',
                        ports=frozenset(), environment=None, volumes=())

            d = gatherResults([RemoteDockerClient(node_1).list(),
                               RemoteDockerClient(node_2).list()])

            def listed(units):
                node_1_list, node_2_list = units
                self.assertEqual([set([unit]), set()],
                                 [node_1_list, node_2_list])

            d.addCallback(listed)
            return d

        d.addCallback(deploy)
        return d
