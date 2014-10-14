# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for moving applications between nodes.
"""
from subprocess import check_output
from yaml import safe_dump

from twisted.python.filepath import FilePath
from twisted.trial.unittest import TestCase

from flocker.node._docker import Unit

from .utils import running_units, require_installed, get_nodes


class MoveTests(TestCase):
    """
    Tests for moving applications between nodes.

    Similar to http://doc-dev.clusterhq.com/gettingstarted/tutorial/
    moving-applications.html#moving-an-application
    """
    @require_installed
    def setUp(self):
        pass

    def test_move(self):
        """
        Test moving an application from one node to another.
        """
        node_1, node_2 = get_nodes(num_nodes=2)
        containers_running_before = {
            node_1: running_units(node_1),
            node_2: running_units(node_2),
        }

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

        check_output([b"flocker-deploy"] +
                     [deployment_config.path] +
                     [application_config.path])

        deployment_moved_config = temp.child(b"deployment.yml")
        deployment_moved_config.setContent(safe_dump({
            u"version": 1,
            u"nodes": {
                node_1: [],
                node_2: [u"mongodb-example"],
            },
        }))

        check_output([b"flocker-deploy"] +
                     [deployment_moved_config.path] +
                     [application_config.path])

        containers_running_after = {
            node_1: running_units(node_1),
            node_2: running_units(node_2),
        }

        new_containers = {
            node_1: set(containers_running_after[node_1]) -
            set(containers_running_before[node_1]),
            node_2: set(containers_running_after[node_2]) -
            set(containers_running_before[node_2]),
        }

        # TODO why is the name not mongodb-example-data like it is in
        # test_deployment?
        expected_new = set([Unit(name=u'mongodb-example',
                                 container_name=u'mongodb-example',
                                 activation_state=u'active',
                                 container_image=u'clusterhq/mongodb:latest',
                                 ports=(), environment=None, volumes=())])

        self.assertEqual(
            new_containers,
            {
                node_1: set(),
                node_2: expected_new
            }
        )
