# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for deploying applications.
"""

import copy

from uuid import uuid4

from pyrsistent import pmap

from twisted.trial.unittest import TestCase

from ..control.httpapi import container_configuration_response

from .testtools import (MONGO_APPLICATION, MONGO_IMAGE,
                        get_mongo_application, require_flocker_cli,
                        require_mongo, create_application,
                        create_attached_volume, require_cluster,
                        require_moving_backend)

from ..testtools import (
    REALISTIC_BLOCKDEVICE_SIZE,
)


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
        if k not in ('host', 'name', 'volumes', 'node_uuid')
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
    timeout = 200

    @require_moving_backend
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
        (node_1, node_1_uuid), (node_2, node_2_uuid) = [
            (node.reported_hostname, node.uuid) for node in cluster.nodes]
        mongo_dataset_id = unicode(uuid4())

        # A mongo db without a quota
        application_1 = create_application(
            MONGO_APPLICATION, MONGO_IMAGE,
            volume=create_attached_volume(
                dataset_id=mongo_dataset_id,
                mountpoint=b'/data/db',
                maximum_size=REALISTIC_BLOCKDEVICE_SIZE,
                metadata=pmap({"name": MONGO_APPLICATION}),
            )
        )

        # A subset of the expected container state dictionary that we expect
        # when the application has been deployed on node_1
        expected_container_1 = container_configuration_response(
            application_1, node_1_uuid
        )
        expected_container_2 = container_configuration_response(
            application_1, node_2_uuid
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
        conf['volume']['maximum_size'] = str(REALISTIC_BLOCKDEVICE_SIZE)

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
        d = cluster.flocker_deploy(
            self, config_deployment_1, config_application_1)

        # Wait for the agent on node1 to create a container with the expected
        # properties.
        waiting_for_container_1 = d.addCallback(
            lambda _: cluster.wait_for_container(
                expected_container_1)
        )

        def got_container_1(actual_container):
            self.assertTrue(actual_container['running'])
            waiting_for_dataset = cluster.wait_for_dataset(
                {
                    u"dataset_id": mongo_dataset_id,
                    u"metadata": None,
                    u"deleted": False,
                    u"maximum_size": REALISTIC_BLOCKDEVICE_SIZE,
                    u"primary": node_1_uuid
                }
            )

            def got_dataset(dataset):
                self.assertEqual(
                    (dataset[u"dataset_id"], dataset[u"maximum_size"]),
                    (mongo_dataset_id, REALISTIC_BLOCKDEVICE_SIZE)
                )
                dataset_deployed = cluster.flocker_deploy(
                    self, config_deployment_2, config_application_1)
                dataset_deployed.addCallback(
                    lambda _: cluster.wait_for_container(expected_container_2)
                )
                return dataset_deployed
            waiting_for_dataset.addCallback(got_dataset)
            return waiting_for_dataset

        waiting_for_container_2 = waiting_for_container_1.addCallback(
            got_container_1)

        def got_container_2(actual_container):
            waiting_for_dataset = cluster.wait_for_dataset(
                {
                    u"dataset_id": mongo_dataset_id,
                    u"metadata": None,
                    u"deleted": False,
                    u"maximum_size": REALISTIC_BLOCKDEVICE_SIZE,
                    u"primary": node_2_uuid
                }
            )

            def got_dataset(dataset):
                self.assertEqual(
                    (dataset[u"dataset_id"], dataset[u"maximum_size"]),
                    (mongo_dataset_id, REALISTIC_BLOCKDEVICE_SIZE)
                )
            waiting_for_dataset.addCallback(got_dataset)
            self.assertTrue(actual_container['running'])
            return waiting_for_dataset

        d = waiting_for_container_2.addCallback(got_container_2)
        return d

    @require_flocker_cli
    @require_mongo
    @require_cluster(1)
    def test_deploy(self, cluster):
        """
        Deploying an application to one node and not another puts the
        application where expected. Where applicable, Docker has internal
        representations of the data given by the configuration files supplied
        to flocker-deploy.
        """
        [node_1] = cluster.nodes

        minimal_deployment = {
            u"version": 1,
            u"nodes": {
                node_1.reported_hostname: [MONGO_APPLICATION],
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

        d = cluster.flocker_deploy(
            self, minimal_deployment, minimal_application)

        d.addCallback(
            lambda _: cluster.assert_expected_deployment(self, {
                node_1.reported_hostname: set([get_mongo_application()]),
            })
        )
        return d
