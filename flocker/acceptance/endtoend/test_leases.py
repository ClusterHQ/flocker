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
            # Give the lease an expiry of 60 seconds.
            pass

        def start_http_container(dataset):
            # In the 60 seconds before the lease expires, we can launch
            # the acceptance tests' data HTTP container and make POST requests
            # to it in a looping call every second.
            # return looping call deferred

        def request_move_dataset(self):
            # We can then request to move the dataset attached to the container.
            return deferred

        def wait_some_amount_of_time(self):
            # Because the dataset is leased, we should be able to continue
            # writing data via HTTP requests to the running container.
            # We should be able to do this for some number of seconds.
            # The looping call running in parallel to this is continuing to
            # write data.

            # wait some time and return a deferred

        def stop_container(self):
            # We stop the container, so that there is no constraint outside
            # of leases to prevent the volume from being unmounted.

            def confirmed_stopped(self):
                # When the container is confirmed as stopped,
                # restart the container again, to prove the dataset
                # hasn't moved.
                # If the dataset had moved, the host path on the volume would
                # have been unmounted. # XXX is this actually true, does
                # Flocker remove mountpoint directories?

        def stop_container_again(self):
            # Stop the container again.

            def stopped_again(self):
                # Ask for the lease to be released, causing the dataset to move.
                # Wait a couple of seconds.

        def try_to_start_again(self):
            # After a couple of seconds, we can try to recreate the container
            # and that should fail, because the host mount path for the volume
            # should no longer exist.
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
