# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for movement of data across nodes.
"""
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure

from twisted.trial.unittest import TestCase

from flocker.testtools import loop_until
from .utils import (flocker_deploy, get_nodes, require_flocker_cli,
                    require_mongo)


class MovingDataTests(TestCase):
    """
    Tests for movement of data across nodes.

    Similar to:
    http://doc-dev.clusterhq.com/gettingstarted/tutorial/volumes.html
    """
    @require_mongo
    @require_flocker_cli
    def test_moving_data(self):
        """
        Moving an application moves that application's data with it. In
        particular, if MongoDB is deployed to a node, and data added to it,
        and then the application is moved to another node, the data remains
        available.
        """
        d = get_nodes(num_nodes=2)

        def deploy_data_application(node_ips):
            node_1, node_2 = node_ips

            application = u"mongodb-volume-example"

            volume_deployment = {
                u"version": 1,
                u"nodes": {
                    node_1: [application],
                    node_2: [],
                },
            }

            volume_application = {
                u"version": 1,
                u"applications": {
                    application: {
                        u"image": u"clusterhq/mongodb",
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

            flocker_deploy(self, volume_deployment, volume_application)

            def create_mongo_client():
                try:
                    return MongoClient(node_1)
                except ConnectionFailure:
                    return False

            d = loop_until(create_mongo_client)
            # TODO look at the timeouts on http://api.mongodb.org/python/current/api/pymongo/mongo_client.html

            def verify_data_moves(client_1):
                database_1 = client_1.example
                database_1.posts.insert({u"the data": u"it moves"})
                data = database_1.posts.find_one()

                volume_deployment_moved = {
                    u"version": 1,
                    u"nodes": {
                        node_1: [],
                        node_2: [application],
                    },
                }

                # TODO Assert that mongo is running in the right place after
                # this:
                # github.com/ClusterHQ/flocker/pull/897#discussion_r19028899
                flocker_deploy(self, volume_deployment_moved,
                               volume_application)

                # TODO use the wait_for_mongo util here
                client_2 = MongoClient(node_2)
                database_2 = client_2.example
                self.assertEqual(data, database_2.posts.find_one())

            d.addCallback(verify_data_moves)
            return d

        d.addCallback(deploy_data_application)
        return d
