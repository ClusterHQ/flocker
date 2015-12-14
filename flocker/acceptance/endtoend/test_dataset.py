# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for the datasets REST API.
"""

from uuid import UUID
from unittest import SkipTest
from time import sleep
from datetime import timedelta

from testtools import run_test_with

from twisted.internet import reactor

from ...common import loop_until
from ...testtools import AsyncTestCase, flaky, async_runner
from ...node.agents.blockdevice import ICloudAPI

from ..testtools import (
    require_cluster, require_moving_backend, create_dataset, DatasetBackend,
    get_backend_api,
)


class DatasetAPITests(AsyncTestCase):
    """
    Tests for the dataset API.
    """

    @flaky(u'FLOC-3207')
    @require_cluster(1)
    def test_dataset_creation(self, cluster):
        """
        A dataset can be created on a specific node.
        """
        return create_dataset(self, cluster)

    @require_cluster(1, required_backend=DatasetBackend.aws)
    def test_dataset_creation_with_gold_profile(self, cluster, backend):
        """
        A dataset created with the gold profile as specified in metadata on EBS
        has EBS volume type 'io1'.

        This is verified by constructing an EBS backend in this process, purely
        for the sake of using it as a wrapper on the cloud API.
        """
        waiting_for_create = create_dataset(
            self, cluster, maximum_size=4*1024*1024*1024,
            metadata={u"clusterhq:flocker:profile": u"gold"})

        def confirm_gold(dataset):
            volumes = backend.list_volumes()
            for volume in volumes:
                if volume.dataset_id == dataset.dataset_id:
                    break
            ebs_volume = backend._get_ebs_volume(volume.blockdevice_id)
            self.assertEqual('io1', ebs_volume.volume_type)

        waiting_for_create.addCallback(confirm_gold)
        return waiting_for_create

    @flaky(u'FLOC-3341')
    @require_moving_backend
    @require_cluster(2)
    def test_dataset_move(self, cluster):
        """
        A dataset can be moved from one node to another.

        All attributes, including the maximum size, are preserved.
        """
        waiting_for_create = create_dataset(self, cluster)

        # Once created, request to move the dataset to node2
        def move_dataset(dataset):
            dataset_moving = cluster.client.move_dataset(
                UUID(cluster.nodes[1].uuid), dataset.dataset_id)

            # Wait for the dataset to be moved; we expect the state to
            # match that of the originally created dataset in all ways
            # other than the location.
            moved_dataset = dataset.set(
                primary=UUID(cluster.nodes[1].uuid))
            dataset_moving.addCallback(
                lambda dataset: cluster.wait_for_dataset(moved_dataset))
            return dataset_moving

        waiting_for_create.addCallback(move_dataset)
        return waiting_for_create

    @flaky(u'FLOC-3196')
    @require_cluster(1)
    def test_dataset_deletion(self, cluster):
        """
        A dataset can be deleted, resulting in its removal from the node.
        """
        created = create_dataset(self, cluster)

        def delete_dataset(dataset):
            deleted = cluster.client.delete_dataset(dataset.dataset_id)

            def not_exists():
                request = cluster.client.list_datasets_state()
                request.addCallback(
                    lambda actual_datasets: dataset.dataset_id not in
                    (d.dataset_id for d in actual_datasets))
                return request
            deleted.addCallback(lambda _: loop_until(reactor, not_exists))
            return deleted
        created.addCallback(delete_dataset)
        return created

    @require_moving_backend
    @run_test_with(async_runner(timeout=timedelta(minutes=6)))
    @require_cluster(2)
    def test_dataset_move_from_dead_node(self, cluster):
        """
        A dataset can be moved from one node to another.

        All attributes, including the maximum size, are preserved.
        """
        api = get_backend_api(self, cluster.cluster_uuid)
        if not ICloudAPI.providedBy(api):
            raise SkipTest(
                "Backend doesn't support ICloudAPI; therefore it might support"
                " moving from dead node but as first pass we assume it "
                "doesn't.")

        # Find a node which is not running the control service.
        # If the control node is shut down we won't be able to move anything!
        node = list(node for node in cluster.nodes
                    if node.public_address !=
                    cluster.control_node.public_address)[0]
        other_node = list(other_node for other_node in cluster.nodes
                          if other_node != node)[0]
        waiting_for_create = create_dataset(self, cluster, node=node)

        def startup_node(node_id):
            api.start_node(node_id)
            # Give node some minimal amount of time to boot so next test
            # is happier:
            sleep(20)

        # Once created, shut down origin node and then request to move the
        # dataset to node2:
        def shutdown(dataset):
            live_node_ids = set(api.list_live_nodes())
            d = node.shutdown()
            # Wait for shutdown to be far enough long that node is down:
            d.addCallback(
                lambda _:
                loop_until(lambda:
                           set(api.list_live_nodes()) == live_node_ids))
            # Schedule node start up:
            d.addCallback(
                lambda _: self.addCleanup(
                    startup_node,
                    (live_node_ids - set(api.list_live_nodes())).pop()))
            d.addCallback(lambda _: dataset)
            return d
        waiting_for_shutdown = waiting_for_create.addCallback(shutdown)

        def move_dataset(dataset):
            dataset_moving = cluster.client.move_dataset(
                UUID(other_node.uuid), dataset.dataset_id)

            # Wait for the dataset to be moved; we expect the state to
            # match that of the originally created dataset in all ways
            # other than the location.
            moved_dataset = dataset.set(
                primary=UUID(other_node.uuid))
            dataset_moving.addCallback(
                lambda dataset: cluster.wait_for_dataset(moved_dataset))
            return dataset_moving

        waiting_for_shutdown.addCallback(move_dataset)
        return waiting_for_shutdown
