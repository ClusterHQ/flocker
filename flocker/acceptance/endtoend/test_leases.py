# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for the datasets REST API.
"""

from uuid import UUID

from twisted.internet.task import LoopingCall
from twisted.trial.unittest import TestCase

from docker.utils import create_host_config

from ...testtools import random_name
from ..testtools import (
    require_cluster, require_moving_backend, create_dataset,
    REALISTIC_BLOCKDEVICE_SIZE, get_docker_client,
    post_http_server, query_http_server, assert_http_server,
)

from ..scripts import SCRIPTS


class LeaseAPITests(TestCase):
    """
    Tests for the leases API.
    """
    @require_moving_backend
    @require_cluster(2)
    def test_lease_prevents_move(self, cluster):
        """
        A dataset cannot be moved if a lease is held on
        it by a particular node.
        """
        client = get_docker_client(cluster, cluster.nodes[0].public_address)
        d = create_dataset(
            self, cluster, maximum_size=REALISTIC_BLOCKDEVICE_SIZE)

        def acquire_lease(dataset):
            # Call the API to acquire a lease with the dataset ID.
            import pdb;pdb.set_trace()
            return cluster.client.acquire_lease(
                dataset.dataset_id, UUID(cluster.nodes[0].uuid))

        d.addCallback(acquire_lease)

        def start_http_container(lease, client):
            # Launch data HTTP container and make POST requests
            # to it in a looping call every second.
            # return looping call deferred
            # script_path = SCRIPTS.child(b"datahttp.py")
            http_port = 8080
            volume_name = random_name(self)
            script = SCRIPTS.child("datahttp.py")
            script_arguments = [u"/data"]
            # XXX how do I attach a dataset here?
            docker_arguments = {
                "host_config": create_host_config(
                    binds=["{}:/data".format(volume_name)],
                    port_bindings={http_port: http_port}),
                "ports": [http_port]}
            container = client.create_container(
                "python:2.7-slim",
                ["python", "-c", script.getContent()] + list(script_arguments),
                **docker_arguments)
            cid = container["Id"]
            client.start(container=cid)
            self.addCleanup(client.remove_container, cid, force=True)

            def loop_write_data():
                data = random_name(self).encode("utf-8")
                d = post_http_server(
                    self, cluster.nodes[0].public_address, http_port,
                    {"data": data}
                )
                d.addCallback(
                    lambda _: assert_http_server(
                        self, cluster.nodes[0].public_address,
                        http_port, expected_response=data
                    )
                )
                return d

            self.loop = LoopingCall(loop_write_data)
            self.loop.start(1)
            import pdb;pdb.set_trace()
            return cid

        d.addCallback(start_http_container, client)
        return d

        """
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
    def test_delete_dataset_after_lease_expiry(self, cluster):
        """
        A dataset can be deleted once a lease held on it by a
        particular node has expired.
        """
        self.fail("not implemented yet")
