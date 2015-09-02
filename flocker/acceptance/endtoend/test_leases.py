# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for the datasets REST API.
"""

# from uuid import UUID

from twisted.trial.unittest import TestCase

from ..testtools import (
    require_cluster, require_moving_backend,  # create_dataset,
    # REALISTIC_BLOCKDEVICE_SIZE,
)


class LeaseAPITests(TestCase):
    """
    Tests for the leases API.
    """
    @require_moving_backend
    # require_cluster should probably delete leases as part of
    # resetting the cluster state between tests
    @require_cluster(2)
    def test_lease_prevents_move(self, cluster):
        """
        A dataset cannot be moved if a lease is held on
        it by a particular node.
        """
        # waiting_for_create = create_dataset(
        #     self, cluster, maximum_size=REALISTIC_BLOCKDEVICE_SIZE)

        # def acquire_lease(dataset):
        #     # Call the API to acquire a lease with the dataset ID.
        #     pass

        # Once created, request to move the dataset to node2
        # def attempt_move_dataset(dataset):
        #     # XXX this should not work
        #     dataset_moving = cluster.client.move_dataset(
        #         UUID(cluster.nodes[1].uuid), dataset.dataset_id)
        #     # XXX what do we do here? we ideally want a confirmation
        #     # from the API that this has failed because we have a lease.
        #     # wait for timeout? no. check the logs? maybe.

        #     return dataset_moving

        # waiting_for_create.addCallback(acquire_lease)
        # waiting_for_create.addCallback(attempt_move_dataset)
        # return waiting_for_create
        self.fail("not implemented yet")

    @require_moving_backend
    @require_cluster(2)
    def test_lease_prevents_delete(self, cluster):
        """
        A dataset cannot be deleted if a lease is held on
        it by a particular node.
        """
        self.fail("not implemented yet")

    @require_moving_backend
    @require_cluster(2)
    def test_move_dataset_after_lease_release(self, cluster):
        """
        A dataset can be moved once a lease held on it by a
        particular node is released.
        """
        self.fail("not implemented yet")

    @require_moving_backend
    @require_cluster(2)
    def test_delete_dataset_after_lease_release(self, cluster):
        """
        A dataset can be deleted once a lease held on it by a
        particular node is released.
        """
        self.fail("not implemented yet")

    @require_moving_backend
    @require_cluster(2)
    def test_move_dataset_after_lease_expiry(self, cluster):
        """
        A dataset can be moved once a lease held on it by a
        particular node has expired.
        """
        self.fail("not implemented yet")

    @require_moving_backend
    @require_cluster(2)
    def test_delete_dataset_after_lease_expiry(self, cluster):
        """
        A dataset can be deleted once a lease held on it by a
        particular node has expired.
        """
        self.fail("not implemented yet")
