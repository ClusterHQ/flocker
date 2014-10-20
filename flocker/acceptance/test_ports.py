# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for communication to applications across nodes.
"""
from pymongo import MongoClient

from twisted.internet.defer import gatherResults
from twisted.trial.unittest import TestCase

from flocker.node._docker import BASE_NAMESPACE, PortMap, Unit

from .utils import (flocker_deploy, get_nodes, RemoteDockerClient,
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
        Deploy an application with an exposed port.
        """
        d = get_nodes(num_nodes=2)

        def deploy_port_application(node_ips):
            self.node_1, self.node_2 = node_ips

            self.internal_port = 27017
            self.external_port = 27018

            self.application = u"mongodb-port-example"
            self.image = u"clusterhq/mongodb"

            application_config = {
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

            deployment_config = {
                u"version": 1,
                u"nodes": {
                    self.node_1: [self.application],
                    self.node_2: [],
                },
            }

            flocker_deploy(self, deployment_config, application_config)

        d.addCallback(deploy_port_application)
        return d

    def test_deployment_with_ports(self):
        """
        Ports are exposed as specified in the application configuration.
        """
        unit = Unit(name=self.application,
                    container_name=BASE_NAMESPACE + self.application,
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
        # There is a potential race condition here
        # TODO Explain how it may manifest, and be fixed
        client_1 = MongoClient(self.node_1, self.external_port)
        database_1 = client_1.example
        database_1.posts.insert({u"the data": u"it moves"})
        data = database_1.posts.find_one()

        client_2 = MongoClient(self.node_2, self.external_port)
        database_2 = client_2.example
        self.assertEqual(data, database_2.posts.find_one())
