# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for deploying applications.
"""
from twisted.trial.unittest import TestCase

from flocker.node._docker import BASE_NAMESPACE, Unit

from .testtools import (assert_expected_deployment, flocker_deploy, get_nodes,
                        MONGO_APPLICATION, MONGO_IMAGE, require_flocker_cli,
                        require_mongo)


class DeploymentTests(TestCase):
    """
    Tests for deploying applications.

    Similar to:
    http://doc-dev.clusterhq.com/gettingstarted/tutorial/
    moving-applications.html#starting-an-application
    """
    @require_flocker_cli
    @require_mongo
    def test_deploy(self):
        """
        Deploying an application to one node and not another puts the
        application where expected. Where applicable, Docker has internal
        representations of the data given by the configuration files supplied
        to flocker-deploy.
        """
        getting_nodes = get_nodes(num_nodes=2)

        def deploy(node_ips):
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

            unit = Unit(name=MONGO_APPLICATION,
                        container_name=BASE_NAMESPACE + MONGO_APPLICATION,
                        activation_state=u'active',
                        container_image=MONGO_IMAGE + u':latest',
                        ports=frozenset([]))

            d = assert_expected_deployment(self, {
                node_1: set([unit]),
                node_2: set([]),
            })

            return d

        getting_nodes.addCallback(deploy)
        return getting_nodes
