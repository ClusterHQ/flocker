# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for deploying applications.
"""

from uuid import uuid4

from pyrsistent import pmap

from twisted.trial.unittest import TestCase

from .testtools import (assert_expected_deployment, flocker_deploy, get_nodes,
                        MONGO_APPLICATION, MONGO_IMAGE, get_mongo_application,
                        require_flocker_cli, require_mongo, create_application,
                        create_attached_volume, get_node_state)


class DeploymentTests(TestCase):
    """
    Tests for deploying applications.

    Similar to:
    http://doc-dev.clusterhq.com/gettingstarted/tutorial/
    moving-applications.html#starting-an-application
    """
    @require_flocker_cli
    def test_application_volume_quotas_changed(self):
        """
        Deploying an application to one node without a defined maximum size
        on its volume and then moving that application to another node with a
        deployment configuration that also does specify a maximum size results
        in the volume being moved and the configured quota size being applied
        on the target node after the volume is successfully received.
        """
        SIZE_100_MB = u"104857600"
        nodes = get_nodes(self, num_nodes=2)
        mongo_dataset_id = unicode(uuid4())

        def mongo_application(maximum_size):
            return create_application(
                MONGO_APPLICATION, MONGO_IMAGE,
                volume=create_attached_volume(
                    dataset_id=mongo_dataset_id,
                    mountpoint=b'/data/db',
                    maximum_size=maximum_size,
                    metadata=pmap({"name": MONGO_APPLICATION}),
                )
            )

        def deploy_with_quotas(nodes):
            node_1, node_2 = nodes
            application = mongo_application(None)
            config_deployment = {
                u"version": 1,
                u"nodes": {
                    node_1: [MONGO_APPLICATION],
                    node_2: [],
                }
            }
            config_application = {
                u"version": 1,
                u"applications": {
                    MONGO_APPLICATION: {
                        u"image": MONGO_IMAGE,
                        u"volume": {
                            u"dataset_id": mongo_dataset_id,
                            u"mountpoint": b"/data/db",
                        }
                    }
                }
            }

            flocker_deploy(self, config_deployment, config_application)
            state = get_node_state(node_1)

            self.assertEqual(application, state[MONGO_APPLICATION])

            # now we've verified the initial deployment has succeeded
            # with the expected result, we will redeploy the same application
            # with new deployment and app configs; the app config will specify
            # a maximum size for the volume and the deployment config will ask
            # flocker to push our app to the second node
            config_deployment[u"nodes"][node_2] = [MONGO_APPLICATION]
            config_deployment[u"nodes"][node_1] = []
            app_config = config_application[u"applications"][MONGO_APPLICATION]
            app_config[u"volume"][u"maximum_size"] = SIZE_100_MB

            flocker_deploy(self, config_deployment, config_application)
            state = get_node_state(node_2)

            application = mongo_application(int(SIZE_100_MB))

            # now we verify that the second deployment has moved the app and
            # flocker-reportstate on the new host gives the expected maximum
            # size for the deployed app's volume
            self.assertEqual(application, state[MONGO_APPLICATION])

        nodes.addCallback(deploy_with_quotas)
        return nodes

    @require_flocker_cli
    def test_application_volume_quotas(self):
        """
        Deploying an application to one node with a defined maximum size
        on its volume and then moving that application to another node with a
        deployment configuration that also specifies the same maximum size
        results in the volume being moved and the configured quota size being
        applied on the target node after the volume is successfully received.
        In other words, the defined volume quota size is preserved from one
        node to the next.
        """
        SIZE_100_MB = u"104857600"
        nodes = get_nodes(self, num_nodes=2)
        mongo_dataset_id = unicode(uuid4())

        def deploy_with_quotas(nodes):
            node_1, node_2 = nodes
            application = create_application(
                MONGO_APPLICATION, MONGO_IMAGE,
                volume=create_attached_volume(
                    dataset_id=mongo_dataset_id,
                    mountpoint=b'/data/db',
                    maximum_size=int(SIZE_100_MB),
                    metadata=pmap({"name": MONGO_APPLICATION}),
                )
            )
            config_deployment = {
                u"version": 1,
                u"nodes": {
                    node_1: [MONGO_APPLICATION],
                    node_2: [],
                }
            }
            config_application = {
                u"version": 1,
                u"applications": {
                    MONGO_APPLICATION: {
                        u"image": MONGO_IMAGE,
                        u"volume": {
                            u"dataset_id": mongo_dataset_id,
                            u"mountpoint": b"/data/db",
                            u"maximum_size": SIZE_100_MB
                        }
                    }
                }
            }

            flocker_deploy(self, config_deployment, config_application)
            state = get_node_state(node_1)
            self.assertEqual(application, state[MONGO_APPLICATION])
            config_deployment[u"nodes"][node_2] = [MONGO_APPLICATION]
            config_deployment[u"nodes"][node_1] = []
            flocker_deploy(self, config_deployment, config_application)
            state = get_node_state(node_2)
            self.assertEqual(application, state[MONGO_APPLICATION])

        nodes.addCallback(deploy_with_quotas)
        return nodes

    @require_flocker_cli
    @require_mongo
    def test_deploy(self):
        """
        Deploying an application to one node and not another puts the
        application where expected. Where applicable, Docker has internal
        representations of the data given by the configuration files supplied
        to flocker-deploy.
        """
        getting_nodes = get_nodes(self, num_nodes=2)

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

            d = assert_expected_deployment(self, {
                node_1: set([get_mongo_application()]),
                node_2: set([]),
            })

            return d

        getting_nodes.addCallback(deploy)
        return getting_nodes
