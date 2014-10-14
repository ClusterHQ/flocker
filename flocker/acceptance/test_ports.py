# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for communication to applications.
"""
from subprocess import check_output
from yaml import safe_dump

# TODO add this to the dev requirements
from pexpect import spawn

from twisted.python.filepath import FilePath
from twisted.trial.unittest import TestCase

from flocker.node._docker import Unit, PortMap

from .utils import running_units, require_installed, get_nodes, flocker_deploy


class PortsTests(TestCase):
    """
    Tests for communication to applications.

    Similar to http://doc-dev.clusterhq.com/gettingstarted/tutorial/
    exposing-ports.html
    """
    @require_installed
    def setUp(self):
        pass

    def test_deployment_with_ports(self):
        """
        Ports specified are shown by docker inspect.
        """
        node_1, node_2 = get_nodes(num_nodes=2)

        temp = FilePath(self.mktemp())
        temp.makedirs()

        application_config = temp.child(b"application.yml")
        application_config.setContent(safe_dump({
            u"version": 1,
            u"applications": {
                u"mongodb-port-example": {
                    u"image": u"clusterhq/mongodb",
                    u"ports": [{
                        u"internal": 27017,
                        u"external": 27017,
                    }],
                },
            },
        }))

        deployment_config = temp.child(b"deployment.yml")
        deployment_config.setContent(safe_dump({
            u"version": 1,
            u"nodes": {
                node_1: [u"mongodb-port-example"],
                node_2: [],
            },
        }))

        flocker_deploy(deployment_config, application_config)

        running = {
            node_1: running_units(node_1),
            node_2: running_units(node_2),
        }

        expected = set([
            Unit(name=u'/mongodb-port-example',
                 container_name=u'/mongodb-port-example',
                 activation_state=u'active',
                 container_image=u'clusterhq/mongodb:latest',
                 ports=frozenset([
                     PortMap(internal_port=27017, external_port=27017)
                 ]),
                 environment=None, volumes=())
        ])

        self.assertEqual(
            running,
            {
                node_1: expected,
                node_2: set(),
            }
        )

    def test_traffic_routed(self):
        """
        An application can be accessed even from a connection to a node
        which it is not running on.
        """
        # TODO Put this stuff in setUp
        node_1, node_2 = get_nodes(num_nodes=2)

        temp = FilePath(self.mktemp())
        temp.makedirs()

        application_config = temp.child(b"application.yml")
        application_config.setContent(safe_dump({
            u"version": 1,
            u"applications": {
                u"mongodb-port-example": {
                    u"image": u"clusterhq/mongodb",
                    u"ports": [{
                        u"internal": 27017,
                        u"external": 27017,
                    }],
                },
            },
        }))

        deployment_config = temp.child(b"deployment.yml")
        deployment_config.setContent(safe_dump({
            u"version": 1,
            u"nodes": {
                node_1: [u"mongodb-port-example"],
                node_2: [],
            },
        }))

        flocker_deploy(deployment_config, application_config)

        child_1 = spawn('mongo ' + node_1)
        child_1.expect('MongoDB shell version:.*')
        child_1.sendline('use example;')
        child_1.expect('switched to db example')
        child_1.sendline('db.records.insert({"flocker": "tested"})')
        child_1.sendline('db.records.find({})')
        child_1.expect('{ "_id" : ObjectId\(".*"\), "flocker" : "tested" }')

        child_2 = spawn('mongo ' + node_2)
        child_2.expect('MongoDB shell version:.*')
        child_2.sendline('use example;')
        child_2.expect('switched to db example')
        child_2.sendline('db.records.find({})')
        child_2.expect('{ "_id" : ObjectId\(".*"\), "flocker" : "tested" }')
