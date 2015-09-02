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

        Might look like this:

        waiting_for_create = create_dataset(
            self, cluster, maximum_size=REALISTIC_BLOCKDEVICE_SIZE)

        def acquire_lease(dataset):
            # Call the API to acquire a lease with the dataset ID.
            pass

        def attempt_move_dataset(dataset):
            pass

        XXX what do we do here? Some options:
        * Modify the dataset configuration API:
          to return an error if the dataset has a lease?

        * Wait and timeout?
          The dataset-agent won't move the dataset because it has a lease so
          the state will not be updated.
          But how do we distinguish this from a dataset move which has not
          yet been performed (delayed for some reason)?

        * Check the dataset-agent logs?
          except that `calculate_changes` doesn't currently log anything if a
          dataset is leased to nodeA but configured to be on nodeB.

        * Don't attempt an acceptance test for this situation.
          It's already tested in the blockdevice API tests...
        """
        self.fail("not implemented yet")

    @require_moving_backend
    @require_cluster(2)
    def test_move_dataset_after_lease_release(self, cluster):
        """
        A dataset can be moved once a lease held on it by a
        particular node is released.

        ...instead we could write only this test which issues the same API
        calls that the Docker Plugin is likely to make eg

        Kubernetes schedules Postgres on NodeA with -v PostgresData
            Docker(NodeA) calls ``VolumePlugin.mount`` PostgresData
                Flongle responds by:
                    Create dataset for FooBar
                    Acquire lease for FooBar on NodeA
            Docker(NodeA) starts Postgres

        Kubernetes schedules Postgres on NodeB with -v PostgresData
            Docker(NodaA) stops container
            Docker(NodeA) calls ``VolumePlugin.umount`` PostgresData
                Flongle releases lease for FooBar on NodeB

            Docker(NodeB) calls ``VolumePlugin.mount`` PostgresData
                Flongle
                    Checks for PostgresData -- exists
                    Checks for PostgresData leases -- none
                    Move PostgresData to NodeB
                    Acquire lease for FooBar on NodeB
            Docker(NodeB) starts Postgres

        @itamarst, is this what you mean by:
        > so perhaps try thinking about leases from point of view of users,
          e.g. docker plugin - how and when will they use it? what would they
          care about?
        """
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
