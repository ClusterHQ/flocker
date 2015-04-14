# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for deploying applications.
"""

import copy

from uuid import uuid4

from pyrsistent import pmap

from twisted.trial.unittest import TestCase

from ..control.httpapi import container_configuration_response

from .testtools import (assert_expected_deployment, flocker_deploy, get_nodes,
                        MONGO_APPLICATION, MONGO_IMAGE, get_mongo_application,
                        require_flocker_cli, require_mongo, create_application,
                        create_attached_volume, require_cluster)

SIZE_100_MB = u"104857600"


def api_configuration_to_flocker_deploy_configuration(api_configuration):
    """
    Convert a dictionary in a format matching the JSON returned by the HTTP
    API to a dictionary in a format matching that used as the value of
    a single application entry in a parsed Flocker configuration.
    """
    deploy_configuration = {
        # Omit the host key when generating the flocker-deploy
        # compatible configuration dictionary
        k: v
        for k, v
        in api_configuration.items()
        if k not in ('host', 'name', 'volumes')
    }
    volumes = api_configuration.get('volumes', [])
    if volumes:
        [volume] = volumes
        deploy_configuration['volume'] = volume
    return deploy_configuration


class DeploymentTests(TestCase):
    """
    Tests for deploying applications.

    Similar to:
    http://doc-dev.clusterhq.com/gettingstarted/tutorial/
    moving-applications.html#starting-an-application
    """
    @require_flocker_cli
    @require_cluster(num_nodes=2)
    def test_application_volume_quotas_changed(self, cluster):
        """
        Deploying an application to one node without a defined maximum size
        on its volume and then moving that application to another node with a
        deployment configuration that also does specify a maximum size results
        in the volume being moved and the configured quota size being applied
        on the target node after the volume is successfully received.
        """
        node_1, node_2 = [node.address for node in cluster.nodes]

        # A mongo db without a quota
        application_1 = create_application(
            MONGO_APPLICATION, MONGO_IMAGE,
            volume=create_attached_volume(
                dataset_id=unicode(uuid4()),
                mountpoint=b'/data/db',
                maximum_size=None,
                metadata=pmap({"name": MONGO_APPLICATION}),
            )
        )

        # A subset of the expected container state dictionary that we expect
        # when the application has been deployed on node_1
        expected_container_1 = container_configuration_response(
            application_1, node_1
        )

        # The first configuration we supply to flocker-deploy
        config_application_1 = {
            u"version": 1,
            u"applications": {
                MONGO_APPLICATION:
                    api_configuration_to_flocker_deploy_configuration(
                        expected_container_1
                    )
            }
        }

        config_deployment_1 = {
            u"version": 1,
            u"nodes": {
                node_1: [MONGO_APPLICATION],
                node_2: [],
            }
        }

        # A mongo db with a 100MB quota
        application_2 = application_1.transform(
            ['volume', 'manifestation', 'dataset', 'maximum_size'],
            SIZE_100_MB
        )

        # A subset of the expected container state dictionary that we expect
        # when the application has been deployed on node_2
        expected_container_2 = container_configuration_response(
            application_2, node_2
        )

        # The second configuration we supply to flocker-deploy
        container_configuration = (
            api_configuration_to_flocker_deploy_configuration(
                expected_container_2)
        )
        config_application_2 = {
            u"version": 1,
            u"applications": {
                MONGO_APPLICATION:
                    copy.deepcopy(container_configuration)
            }
        }

        conf = config_application_2[u'applications'][MONGO_APPLICATION]
        conf['volume']['maximum_size'] = SIZE_100_MB

        config_deployment_2 = {
            u"version": 1,
            u"nodes": {
                node_1: [],
                node_2: [MONGO_APPLICATION],
            }
        }

        # Do the first deployment
        flocker_deploy(self, config_deployment_1, config_application_1)

        # Wait for the agent on node1 to create a container with the expected
        # properties.
        waiting_for_container_1 = cluster.wait_for_container(
            expected_container_1)

        def got_container_1(result):
            cluster, actual_container = result
            self.assertTrue(actual_container['running'])
            # Do the second deployment
            flocker_deploy(self, config_deployment_2, config_application_2)
            return cluster.wait_for_container(expected_container_2)

        waiting_for_container_2 = waiting_for_container_1.addCallback(
            got_container_1)

        def got_container_2(result):
            cluster, actual_container = result
            dataset_id = actual_container['volumes'][0]['dataset_id']
            waiting_for_dataset = cluster.wait_for_dataset(
                {
                    u"dataset_id": dataset_id,
                    u"metadata": None,
                    u"deleted": False,
                    u"maximum_size": int(SIZE_100_MB),
                    u"primary": node_2
                }
            )

            def got_dataset(result):
                cluster, dataset = result
                self.assertEqual(
                    (dataset[u"dataset_id"], dataset[u"maximum_size"]),
                    (dataset_id, int(SIZE_100_MB))
                )
            waiting_for_dataset.addCallback(got_dataset)
            self.assertTrue(actual_container['running'])
            return waiting_for_dataset

        d = waiting_for_container_2.addCallback(got_container_2)
        return d

    @require_flocker_cli
    @require_cluster(num_nodes=2)
    def test_application_volume_quotas(self, cluster):
        """
        Deploying an application to one node with a defined maximum size
        on its volume and then moving that application to another node with a
        deployment configuration that also specifies the same maximum size
        results in the volume being moved and the configured quota size being
        applied on the target node after the volume is successfully received.
        In other words, the defined volume quota size is preserved from one
        node to the next.
        """
        node_1, node_2 = [node.address for node in cluster.nodes]
        mongo_dataset_id = unicode(uuid4())

        # A mongo db without a quota
        application_1 = create_application(
            MONGO_APPLICATION, MONGO_IMAGE,
            volume=create_attached_volume(
                dataset_id=mongo_dataset_id,
                mountpoint=b'/data/db',
                maximum_size=int(SIZE_100_MB),
                metadata=pmap({"name": MONGO_APPLICATION}),
            )
        )

        # A subset of the expected container state dictionary that we expect
        # when the application has been deployed on node_1
        expected_container_1 = container_configuration_response(
            application_1, node_1
        )
        expected_container_2 = container_configuration_response(
            application_1, node_2
        )

        container_configuration_1 = (
            api_configuration_to_flocker_deploy_configuration(
                expected_container_1
            )
        )

        # The first configuration we supply to flocker-deploy
        config_application_1 = {
            u"version": 1,
            u"applications": {
                MONGO_APPLICATION:
                    copy.deepcopy(container_configuration_1)
            }
        }

        conf = config_application_1[u'applications'][MONGO_APPLICATION]
        conf['volume']['maximum_size'] = SIZE_100_MB

        config_deployment_1 = {
            u"version": 1,
            u"nodes": {
                node_1: [MONGO_APPLICATION],
                node_2: [],
            }
        }

        config_deployment_2 = {
            u"version": 1,
            u"nodes": {
                node_1: [],
                node_2: [MONGO_APPLICATION],
            }
        }

        # Do the first deployment
        flocker_deploy(self, config_deployment_1, config_application_1)

        # Wait for the agent on node1 to create a container with the expected
        # properties.
        waiting_for_container_1 = cluster.wait_for_container(
            expected_container_1)

        def got_container_1(result):
            cluster, actual_container = result
            self.assertTrue(actual_container['running'])
            waiting_for_dataset = cluster.wait_for_dataset(
                {
                    u"dataset_id": mongo_dataset_id,
                    u"metadata": None,
                    u"deleted": False,
                    u"maximum_size": int(SIZE_100_MB),
                    u"primary": node_1
                }
            )

            def got_dataset(result):
                cluster, dataset = result
                self.assertEqual(
                    (dataset[u"dataset_id"], dataset[u"maximum_size"]),
                    (mongo_dataset_id, int(SIZE_100_MB))
                )
                flocker_deploy(self, config_deployment_2, config_application_1)
                return cluster.wait_for_container(expected_container_2)
            waiting_for_dataset.addCallback(got_dataset)
            return waiting_for_dataset

        waiting_for_container_2 = waiting_for_container_1.addCallback(
            got_container_1)

        def got_container_2(result):
            cluster, actual_container = result
            waiting_for_dataset = cluster.wait_for_dataset(
                {
                    u"dataset_id": mongo_dataset_id,
                    u"metadata": None,
                    u"deleted": False,
                    u"maximum_size": int(SIZE_100_MB),
                    u"primary": node_2
                }
            )

            def got_dataset(result):
                cluster, dataset = result
                self.assertEqual(
                    (dataset[u"dataset_id"], dataset[u"maximum_size"]),
                    (mongo_dataset_id, int(SIZE_100_MB))
                )
            waiting_for_dataset.addCallback(got_dataset)
            self.assertTrue(actual_container['running'])
            return waiting_for_dataset

        d = waiting_for_container_2.addCallback(got_container_2)
        return d

    @require_flocker_cli
    @require_mongo
    def test_deploy(self):
        """
        Deploying an application to one node and not another puts the
        application where expected. Where applicable, Docker has internal
        representations of the data given by the configuration files supplied
        to flocker-deploy.
        """
        getting_nodes = get_nodes(self, num_nodes=1)

        def deploy(node_ips):
            [node_1] = node_ips

            minimal_deployment = {
                u"version": 1,
                u"nodes": {
                    node_1: [MONGO_APPLICATION],
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
            })

            return d

        getting_nodes.addCallback(deploy)
        return getting_nodes
