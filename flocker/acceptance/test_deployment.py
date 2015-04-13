# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for deploying applications.
"""

from uuid import uuid4

from pyrsistent import pmap

from twisted.trial.unittest import TestCase

from ..control.httpapi import container_configuration_response

from .testtools import (assert_expected_deployment, flocker_deploy, get_nodes,
                        MONGO_APPLICATION, MONGO_IMAGE, get_mongo_application,
                        require_flocker_cli, require_mongo, create_application,
                        create_attached_volume, get_node_state,
                        get_test_cluster, require_cluster)

SIZE_100_MB = u"104857600"

def api_configuration_to_flocker_deploy_configuration(api_configuration):
    deploy_configuration = {
        # Omit the host key when generating the flocker-deploy
        # compatible configuration dictionary
        k: v
        for k,v
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
                MONGO_APPLICATION: api_configuration_to_flocker_deploy_configuration(expected_container_1)
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
        config_application_2 = {
            u"version": 1,
            u"applications": {
                MONGO_APPLICATION: api_configuration_to_flocker_deploy_configuration(expected_container_2)
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
        waiting_for_container_1 = cluster.wait_for_container(expected_container_1)

        def got_container_1(result):
            cluster, actual_container = result
            self.assertTrue(actual_container['running'])
            # Do the second deployment
            flocker_deploy(self, config_deployment_2, config_application_2)
            return cluster.wait_for_container(expected_container_2)

        waiting_for_container_2 = waiting_for_container_1.addCallback(got_container_1)

        def got_container_2(result):
            cluster, actual_container = result
            self.assertTrue(actual_container['running'])

        d = waiting_for_container_2.addCallback(got_container_2)
        return d

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
            d = get_test_cluster()
            d.addCallback(get_node_state, node_1)

            def got_state(result):
                cluster, state = result
                state[MONGO_APPLICATION].pop("running")
                self.assertEqual(
                    container_configuration_response(application, node_1),
                    state[MONGO_APPLICATION]
                )
                config_deployment[u"nodes"][node_2] = [MONGO_APPLICATION]
                config_deployment[u"nodes"][node_1] = []
                flocker_deploy(self, config_deployment, config_application)
                return get_node_state(cluster, node_2)
            d.addCallback(got_state)

            def got_second_state(result):
                _, state = result
                state[MONGO_APPLICATION].pop("running")
                self.assertEqual(
                    container_configuration_response(application, node_2),
                    state[MONGO_APPLICATION]
                )
            d.addCallback(got_second_state)
            return d

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
