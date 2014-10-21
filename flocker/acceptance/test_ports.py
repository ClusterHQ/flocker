# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for communication to applications across nodes.
"""
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure

from twisted.trial.unittest import TestCase

from flocker.node._docker import BASE_NAMESPACE, PortMap, Unit

from flocker.testtools import loop_until

from .utils import (assertExpectedDeployment, flocker_deploy, get_nodes,
                    require_flocker_cli, require_mongo)


class PortsTests(TestCase):
    """
    Tests for communication to applications across nodes.

    Similar to:
    http://doc-dev.clusterhq.com/gettingstarted/tutorial/exposing-ports.html
    """
    @require_flocker_cli
    def setUp(self):
        """
        Deploy an application with an internal port mapped to a different
        external port.
        """
        d = get_nodes(num_nodes=2)

        def deploy_port_application(node_ips):
            self.node_1, self.node_2 = node_ips

            self.internal_port = 27017
            self.external_port = 27018

            self.application = u"mongodb-port-example"
            self.image = u"clusterhq/mongodb"

            port_deployment = {
                u"version": 1,
                u"nodes": {
                    self.node_1: [self.application],
                    self.node_2: [],
                },
            }

            port_application = {
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
            }

            flocker_deploy(self, port_deployment, port_application)

        d.addCallback(deploy_port_application)
        return d

    def test_deployment_with_ports(self):
        """
        Ports are exposed as specified in the application configuration.
        Docker has internal representations of the port mappings given by the
        configuration files supplied to flocker-deploy.
        """
        unit = Unit(name=self.application,
                    container_name=BASE_NAMESPACE + self.application,
                    activation_state=u'active',
                    container_image=self.image + u':latest',
                    ports=frozenset([
                        PortMap(internal_port=self.internal_port,
                                external_port=self.external_port)
                    ]))

        d = assertExpectedDeployment(self, {
            self.node_1: set([unit]),
            self.node_2: set([]),
        })

        return d

    @require_mongo
    def test_traffic_routed(self):
        """
        An application can be accessed even from a connection to a node
        which it is not running on. In particular, if MongoDB is deployed to a
        node, and data added to it, that data is visible when a client connects
        to a different node on the cluster.
        """
        def create_mongo_client():
            try:
                return MongoClient(self.node_1, self.external_port)
            except ConnectionFailure:
                return False

        # TODO Make this whole loop a test utility
        d = loop_until(create_mongo_client)

        def verify_traffic_routed(client_1):
            posts_1 = client_1.example.posts
            posts_1.insert({u"the data": u"it moves"})

            self.assertEqual(
                posts_1.find_one(),
                MongoClient(self.node_2,
                            self.external_port).example.posts.find_one()
            )

        d.addCallback(verify_traffic_routed)
        return d
