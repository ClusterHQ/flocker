# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for moving applications between nodes.
"""
from twisted.trial.unittest import TestCase

from .testtools import (assert_expected_deployment, flocker_deploy,
                        get_clean_nodes, MONGO_APPLICATION, MONGO_IMAGE,
                        get_mongo_application, require_flocker_cli)


class MovingApplicationTests(TestCase):
    """
    Tests for moving applications between nodes.

    Similar to http://doc-dev.clusterhq.com/gettingstarted/tutorial/
    moving-applications.html#moving-an-application
    """
    @require_flocker_cli
    def test_moving_application(self):
        """
        After deploying an application to one node and then moving it onto
        another node, it is only on the second node. This only tests that the
        application is present with the given name and image on a second node
        after it has been moved from the first.
        """
        getting_nodes = get_clean_nodes(self, num_nodes=2)

        def deploy_and_move(node_ips):
            node_1, node_2 = node_ips

            minimal_deployment = {
                u"version": 1,
                u"nodes": {
                    node_1: [MONGO_APPLICATION],
                    node_2: [],
                },
            }

            minimal_application = {
                u"version": 1,
                u"applications": {
                    MONGO_APPLICATION: {
                        u"image": MONGO_IMAGE,
                    },
                },
            }

            flocker_deploy(self, minimal_deployment, minimal_application)

            minimal_deployment_moved = {
                u"version": 1,
                u"nodes": {
                    node_1: [],
                    node_2: [MONGO_APPLICATION],
                },
            }

            flocker_deploy(self, minimal_deployment_moved, minimal_application)

            d = assert_expected_deployment(self, {
                node_1: set([]),
                node_2: set([get_mongo_application()])
            })

            return d

        getting_nodes.addCallback(deploy_and_move)
        return getting_nodes
