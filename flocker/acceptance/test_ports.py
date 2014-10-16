# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for communication to applications across nodes.
"""
from yaml import safe_dump

from pexpect import spawn

from twisted.internet.defer import gatherResults
from twisted.python.filepath import FilePath
from twisted.trial.unittest import TestCase

from flocker.node._docker import PortMap, RemoteDockerClient, Unit

from .utils import (flocker_deploy, get_nodes, require_flocker_cli,
                    require_mongo)


class PortsTests(TestCase):
    """
    Tests for communication to applications across nodes.

    Similar to:
    http://doc-dev.clusterhq.com/gettingstarted/tutorial/exposing-ports.html
    """
    @require_flocker_cli
    def setUp(self):
        """
        Deploy an application with an exposed port.
        """
        d = get_nodes(num_nodes=2)

        def deploy_port_application(node_ips):
            self.node_1, self.node_2 = node_ips

            self.internal_port = 27017
            self.external_port = 27017

            self.application = u"mongodb-port-example"
            self.image = u"clusterhq/mongodb"

            temp = FilePath(self.mktemp())
            temp.makedirs()
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

        d.addCallback(deploy_port_application)
        return d

    def test_deployment_with_ports(self):
        """
        Ports are exposed as specified in the application configuration.
        """
        unit = Unit(name=self.application,
                    # TODO Here and other places use BASE_NAMESPACE from
                    # _docker
                    container_name=u'flocker--' + self.application,
                    activation_state=u'active',
                    container_image=self.image + u':latest',
                    ports=frozenset([
                        PortMap(internal_port=self.internal_port,
                                external_port=self.external_port)
                    ]),
                    environment=None, volumes=())

        d = gatherResults([RemoteDockerClient(self.node_1).list(),
                           RemoteDockerClient(self.node_2).list()])

        def listed(units):
            node_1_list, node_2_list = units
            self.assertEqual([set([unit]), set()],
                             [node_1_list, node_2_list])

        d.addCallback(listed)
        return d

    @require_mongo
    def test_traffic_routed(self):
        """
        An application can be accessed even from a connection to a node
        which it is not running on.

        Instead of pexpect this could use PyMongo, which would mean that the
        mongo client would not have to be installed. However, this uses
        pexpect to be as close as possible to the tutorial.
        """
        child_1 = spawn('mongo ' + self.node_1)
        # The docs say "If you get a connection refused error try again after
        # a few seconds; the application might take some time to fully start
        # up.". If this problem manifests here, program that with an except
        # clause (I think for pexpect.EOF).
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
