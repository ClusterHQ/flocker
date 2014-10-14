# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for communication to applications.
"""
from yaml import safe_dump

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
        """
        Deploy an application with an exposed port.
        """
        self.node_1, self.node_2 = get_nodes(num_nodes=2)

        temp = FilePath(self.mktemp())
        temp.makedirs()

        self.internal_port = 27017
        self.external_port = 27017

        self.application = u"mongodb-port-example"
        self.image = u"clusterhq/mongodb"

        application_config = temp.child(b"application.yml")
        application_config.setContent(safe_dump({
            u"version": 1,
            u"applications": {
                self.application: {
                    u"image": self.image,
                    u"ports": [{
                        u"internal": self.internal_port,
                        u"external": self.external_port,
                    }],
                },
            },
        }))

        deployment_config = temp.child(b"deployment.yml")
        deployment_config.setContent(safe_dump({
            u"version": 1,
            u"nodes": {
                self.node_1: [self.application],
                self.node_2: [],
            },
        }))

        flocker_deploy(deployment_config, application_config)

    def test_deployment_with_ports(self):
        """
        Ports are exposed.
        """
        unit = Unit(name=u'/' + self.application,
                    container_name=u'/' + self.application,
                    activation_state=u'active',
                    container_image=self.image + u':latest',
                    ports=frozenset([
                        PortMap(internal_port=self.internal_port,
                                external_port=self.external_port)
                    ]),
                    environment=None, volumes=())

        self.assertEqual(
            [running_units(self.node_1), running_units(self.node_2)],
            [set([unit]), set()]
        )

    def test_traffic_routed(self):
        """
        An application can be accessed even from a connection to a node
        which it is not running on.
        """
        # TODO Test that mongo is installed and give an appropriate error
        # if it is not
        child_1 = spawn('mongo ' + self.node_1)
        child_1.expect('MongoDB shell version:.*')
        child_1.sendline('use example;')
        child_1.expect('switched to db example')
        child_1.sendline('db.records.insert({"flocker": "tested"})')
        child_1.sendline('db.records.find({})')
        child_1.expect('{ "_id" : ObjectId\(".*"\), "flocker" : "tested" }')

        child_2 = spawn('mongo ' + self.node_2)
        child_2.expect('MongoDB shell version:.*')
        child_2.sendline('use example;')
        child_2.expect('switched to db example')
        child_2.sendline('db.records.find({})')
        child_2.expect('{ "_id" : ObjectId\(".*"\), "flocker" : "tested" }')
