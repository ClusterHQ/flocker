# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for movement of data across nodes.
"""
from twisted.trial.unittest import TestCase

from .testtools import (flocker_deploy, get_mongo_client, get_nodes,
                        MONGO_APPLICATION, MONGO_IMAGE, require_flocker_cli,
                        require_mongo)


class MovingDataTests(TestCase):
    """
    Tests for movement of data across nodes.

    Similar to:
    http://doc-dev.clusterhq.com/gettingstarted/tutorial/volumes.html
    """
    @require_flocker_cli
    @require_mongo
    def test_moving_data(self):
        """
        Moving an application moves that application's data with it. In
        particular, if MongoDB is deployed to a node, and data added to it,
        and then the application is moved to another node, the data remains
        available.
        """
        getting_nodes = get_nodes(self, num_nodes=2)

        volume_application = {
            u"version": 1,
            u"applications": {
                MONGO_APPLICATION: {
                    u"image": MONGO_IMAGE,
                    u"ports": [{
                        u"internal": 27017,
                        u"external": 27017,
                    }],
                    u"volume": {
                        # The location within the container where the data
                        # volume will be mounted:
                        u"mountpoint": u"/data/db"
                    }
                },
            },
        }

        def deploy_data_application(node_ips):
            self.node_1, self.node_2 = node_ips

            volume_deployment = {
                u"version": 1,
                u"nodes": {
                    self.node_1: [MONGO_APPLICATION],
                    self.node_2: [],
                },
            }

            flocker_deploy(self, volume_deployment, volume_application)

        deploying = getting_nodes.addCallback(deploy_data_application)

        getting_client = deploying.addCallback(
            lambda _: get_mongo_client(self.node_1))

        def verify_data_moves(client_1):
            database_1 = client_1.example
            database_1.posts.insert({u"the data": u"it moves"})
            data = database_1.posts.find_one()

            volume_deployment_moved = {
                u"version": 1,
                u"nodes": {
                    self.node_1: [],
                    self.node_2: [MONGO_APPLICATION],
                },
            }

            flocker_deploy(self, volume_deployment_moved, volume_application)

            d = get_mongo_client(self.node_2)

            d.addCallback(lambda client_2: self.assertEqual(
                data,
                client_2.example.posts.find_one()))

            return d

        verifying = getting_client.addCallback(verify_data_moves)
        return verifying
