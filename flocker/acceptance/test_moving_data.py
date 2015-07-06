# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for movement of data across nodes.
"""
from twisted.trial.unittest import TestCase

from pyrsistent import thaw, freeze

from .testtools import (get_mongo_client, require_cluster,
                        MONGO_APPLICATION, MONGO_IMAGE, require_flocker_cli,
                        require_mongo, require_moving_backend)


class MovingDataTests(TestCase):
    """
    Tests for movement of data across nodes.
    """
    @require_flocker_cli
    @require_mongo
    @require_moving_backend
    @require_cluster(2)
    def test_moving_data(self, cluster):
        """
        Moving an application moves that application's data with it. In
        particular, if MongoDB is deployed to a node, and data added to it,
        and then the application is moved to another node, the data remains
        available.
        """
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

        volume_application_different_port = thaw(freeze(
            volume_application).transform(
                [u"applications", MONGO_APPLICATION, u"ports", 0,
                 u"external"], 27018))

        node_1, node_2 = cluster.nodes

        volume_deployment = {
            u"version": 1,
            u"nodes": {
                node_1.reported_hostname: [MONGO_APPLICATION],
                node_2.reported_hostname: [],
            },
        }

        deployed = cluster.flocker_deploy(
            self, volume_deployment, volume_application)

        deployed.addCallback(
            lambda _: get_mongo_client(node_1.public_address)
        )

        def verify_data_moves(client_1):
            database_1 = client_1.example
            database_1.posts.insert({u"the data": u"it moves"})
            data = database_1.posts.find_one()

            volume_deployment_moved = {
                u"version": 1,
                u"nodes": {
                    node_1.reported_hostname: [],
                    node_2.reported_hostname: [MONGO_APPLICATION],
                },
            }

            # Use different port so we're sure it's new container we're
            # talking to:
            moved = cluster.flocker_deploy(
                self, volume_deployment_moved,
                volume_application_different_port
            )

            moved.addCallback(
                lambda _: get_mongo_client(node_2.public_address, 27018))

            moved.addCallback(lambda client_2: self.assertEqual(
                data,
                client_2.example.posts.find_one()))

            return moved

        deployed.addCallback(verify_data_moves)
        return deployed
