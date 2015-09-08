# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for the datasets REST API.
"""

from uuid import UUID, uuid4

from twisted.trial.unittest import TestCase

from docker.utils import create_host_config

from ...testtools import random_name, loop_until
from ..testtools import (
    require_cluster, require_moving_backend, create_dataset,
    REALISTIC_BLOCKDEVICE_SIZE, get_docker_client,
    post_http_server, assert_http_server,
)
from ...apiclient import LeaseAlreadyHeld
from ..scripts import SCRIPTS


class LeaseAPITests(TestCase):
    """
    Tests for the leases API.
    """
    def _assert_lease_behavior(self, cluster, operation,
                               additional_kwargs, state_method,
                               expire_lease=False):
        if expire_lease:
            lease_expiry = 60
        else:
            lease_expiry = None
        http_port = 8080
        dataset_id = uuid4()
        datasets = []
        leases = []
        client = get_docker_client(cluster, cluster.nodes[0].public_address)
        d = create_dataset(
            self, cluster, maximum_size=REALISTIC_BLOCKDEVICE_SIZE,
            dataset_id=dataset_id
        )

        def acquire_lease(dataset):
            # Call the API to acquire a lease with the dataset ID.
            datasets.insert(0, dataset)
            acquiring_lease = cluster.client.acquire_lease(
                dataset.dataset_id, UUID(cluster.nodes[0].uuid),
                expires=lease_expiry
            )

            def get_dataset_path(lease, created_dataset):
                leases.insert(0, lease)
                getting_datasets = cluster.client.list_datasets_state()

                def extract_dataset_path(datasets):
                    return datasets[0].path

                getting_datasets.addCallback(extract_dataset_path)
                return getting_datasets

            acquiring_lease.addCallback(get_dataset_path, dataset)
            return acquiring_lease

        d.addCallback(acquire_lease)

        def start_http_container(dataset_path, client):
            # Launch data HTTP container and make POST requests
            # to it in a looping call every second.
            # return looping call deferred
            script = SCRIPTS.child("datahttp.py")
            script_arguments = [u"/data"]
            docker_arguments = {
                "host_config": create_host_config(
                    binds=["{}:/data".format(dataset_path.path)],
                    port_bindings={http_port: http_port}),
                "ports": [http_port],
                "volumes": [u"/data"]}
            container = client.create_container(
                "python:2.7-slim",
                ["python", "-c", script.getContent()] + list(script_arguments),
                **docker_arguments)
            cid = container["Id"]
            client.start(container=cid)
            self.addCleanup(client.remove_container, cid, force=True)
            return cid

        d.addCallback(start_http_container, client)

        def write_data(container_id):
            data = random_name(self).encode("utf-8")
            writing = post_http_server(
                self, cluster.nodes[0].public_address, http_port,
                {"data": data}
            )
            writing.addCallback(
                lambda _: assert_http_server(
                    self, cluster.nodes[0].public_address,
                    http_port, expected_response=data
                )
            )

            writing.addCallback(lambda _: container_id)
            return writing

        d.addCallback(write_data)

        def stop_container(container_id, client, dataset_id):
            # This ensures Docker hasn't got a lock on the volume that
            # might prevent it being moved separate to the lock held by
            # the lease.
            client.stop(container_id)
            operation_dataset_request = operation(
                dataset_id=dataset_id, **additional_kwargs)
            operation_dataset_request.addCallback(
                lambda new_dataset: datasets.insert(0, new_dataset))
            operation_dataset_request.addCallback(lambda _: container_id)
            return operation_dataset_request

        d.addCallback(stop_container, client, dataset_id)

        def restart_container(container_id, client, cluster):
            client.start(container=container_id)
            return container_id

        d.addCallback(restart_container, client, cluster)

        d.addCallback(write_data)

        def stop_container_again(container_id, client, dataset_id):
            client.stop(container_id)
            if lease_expiry:
                # wait for lease to expire
                acquiring_lease = cluster.client.acquire_lease(
                    dataset_id,
                    UUID(cluster.nodes[0].uuid),
                    expires=lease_expiry
                )
                # At this point the lease must still be valid and our request
                # should raise an exception.
                acquiring_lease.addCallback(
                    lambda _: self.fail('Lease expired too soon.')
                )
                # Trap the expected failure and move on down the callback chain
                acquiring_lease.addErrback(
                    lambda failure: failure.trap(LeaseAlreadyHeld)
                )

                [expected_lease] = leases

                # loop until lease expires
                def lease_removed():
                    d = cluster.client.list_leases()

                    def got_leases(leases):
                        return expected_lease not in leases
                    d.addCallback(got_leases)
                    return d
                return loop_until(lease_removed)
            else:
                releasing = cluster.client.release_lease(dataset_id)
                releasing.addCallback(lambda _: container_id)
                # Now we've released the lease and stopped the running
                # container, our earlier move request should be enacted
                # after a short delay.
                return releasing

        d.addCallback(stop_container_again, client, dataset_id)

        def dataset_moved(_):
            waiting = state_method(datasets[0])
            return waiting

        d.addCallback(dataset_moved)

        return d

    @require_moving_backend
    @require_cluster(2)
    def test_lease_prevents_move(self, cluster):
        """
        A dataset cannot be moved if a lease is held on
        it by a particular node.
        """
        return self._assert_lease_behavior(
            cluster,
            cluster.client.move_dataset,
            {'primary': cluster.nodes[1].uuid},
            cluster.wait_for_dataset,
            expire_lease=False,
        )

    @require_moving_backend
    @require_cluster(2)
    def test_lease_prevents_delete(self, cluster):
        """
        A dataset cannot be deleted if a lease is held on
        it by a particular node.
        """
        return self._assert_lease_behavior(
            cluster,
            cluster.client.delete_dataset,
            {},
            cluster.wait_for_deleted_dataset,
            expire_lease=False,
        )
