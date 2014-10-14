# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for moving applications between nodes.
"""
from yaml import safe_dump

from twisted.python.filepath import FilePath
from twisted.trial.unittest import TestCase

from flocker.node._docker import Unit

from .utils import running_units, require_installed, get_nodes, flocker_deploy


class MoveTests(TestCase):
    """
    Tests for moving applications between nodes.

    Similar to http://doc-dev.clusterhq.com/gettingstarted/tutorial/
    moving-applications.html#moving-an-application
    """
    @require_installed
    def setUp(self):
        pass

    def test_moving(self):
        """
        After deploying an application to one node and then moving it onto
        another node, it is only on the second node.
        """
        node_1, node_2 = get_nodes(num_nodes=2)

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

        deployment_moved_config = temp.child(b"deployment.yml")
        deployment_moved_config.setContent(safe_dump({
            u"version": 1,
            u"nodes": {
                node_1: [],
                node_2: [u"mongodb-example"],
            },
        }))

        flocker_deploy(deployment_moved_config, application_config)

        unit = Unit(name=u'/mongodb-example',
                    container_name=u'/mongodb-example',
                    activation_state=u'active',
                    container_image=u'clusterhq/mongodb:latest',
                    ports=frozenset(), environment=None, volumes=())

        self.assertEqual(
            [running_units(node_1), running_units(node_2)],
            [set(), set([unit])]
        )
