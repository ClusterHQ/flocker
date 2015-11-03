# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for the datasets REST API.
"""

from uuid import UUID
from unittest import skipUnless

from twisted.internet import reactor
from twisted.trial.unittest import TestCase

from ...common import loop_until

from ..testtools import (
    require_cluster, require_moving_backend, create_dataset, DatasetBackend
)

STORAGE_PROFILES_IMPLEMENTED = False


class DatasetAPITests(TestCase):
    """
    Tests for the dataset API.
    """
    @require_cluster(1)
    def test_dataset_creation(self, cluster):
        """
        A dataset can be created on a specific node.
        """
        return create_dataset(self, cluster)

    @skipUnless(STORAGE_PROFILES_IMPLEMENTED,
                "Flocker storage profiles are not implemented yet.")
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
            self.assertEqual('io1', ebs_volume.type)

        waiting_for_create.addCallback(confirm_gold)
        return waiting_for_create

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
