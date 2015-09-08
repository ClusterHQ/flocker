# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for the leases API.
"""

from uuid import UUID, uuid4

from twisted.internet import reactor
from twisted.internet.task import deferLater
from twisted.trial.unittest import TestCase

from docker.utils import create_host_config

from ...testtools import random_name
from ..testtools import (
    require_cluster, require_moving_backend, create_dataset,
    REALISTIC_BLOCKDEVICE_SIZE, get_docker_client,
    post_http_server, assert_http_server,
)
from ..scripts import SCRIPTS


class LeaseAPITests(TestCase):
    """
    Tests for the leases API.
    """
    timeout = 600

    def _assert_lease_behavior(self, cluster, operation,
                               additional_kwargs, state_method):
        """
        Assert that leases prevent datasets from being moved or deleted.

        * Create a dataset on node1.
        * Acquire a lease for dataset on node1.
        * Start a container (directly using docker-py) bind mounted to dataset
          mount point on node1 and verify that data can be written.
        * Stop the container.
        * Request a move or delete operation.
        * Wait for a short time; enough time for an unexpected unmount to take
          place.
        * Restart the container and write data to it, to demonstrate that the
          dataset is still mounted and writable.
        * Stop the container again.
        * Release the lease, allowing the previously requested operation to
          proceed.
        * Wait for the previously requested operation to complete.

        :param Cluster cluster: The cluster on which to operate.
        :param operation: The ``FlockerClient`` method to call before releasing
            the lease.
        :param dict additional_kwargs: Any additional arguments to pass to
            ``operation``.
        :param state_method: A callable which returns a ``Deferred`` that fires
            when the requested operation has been performed.
        :returns: A ``Deferred`` that fires when the all the steps have
            completed.
        """
        http_port = 8080
        dataset_id = uuid4()
        datasets = []
        leases = []
        containers = []
        client = get_docker_client(cluster, cluster.nodes[0].public_address)

        creating_dataset = create_dataset(
            self, cluster, maximum_size=REALISTIC_BLOCKDEVICE_SIZE,
            dataset_id=dataset_id
        )

        def get_dataset_state(configured_dataset):
            """
            XXX: This shouldn't really be needed because ``create_dataset``
            returns ``wait_for_dataset`` which returns the dataset state, but
            unfortunately ``wait_for_dataset`` wipes out the dataset path for
            comparison purposes.
            """
            d = cluster.client.list_datasets_state()
            d.addCallback(
                lambda dataset_states: [
                    dataset_state
                    for dataset_state in dataset_states
                    if dataset_state.dataset_id == dataset_id
                ][0]
            )
            d.addCallback(
                lambda dataset: datasets.insert(0, dataset)
            )
            return d
        getting_dataset_state = creating_dataset.addCallback(
            get_dataset_state
        )

        def acquire_lease(ignored):
            # Call the API to acquire a lease with the dataset ID.
            d = cluster.client.acquire_lease(
                dataset_id, UUID(cluster.nodes[0].uuid),
                # Lease will never expire
                expires=None
            )
            d.addCallback(lambda lease: leases.insert(0, lease))
            return d
        acquiring_lease = getting_dataset_state.addCallback(acquire_lease)

        def start_http_container(ignored):
            """
            Launch data HTTP container and make POST requests
            to it in a looping call every second.
            return looping call deferred
            """
            [dataset] = datasets
            script = SCRIPTS.child("datahttp.py")
            script_arguments = [u"/data"]
            docker_arguments = {
                "host_config": create_host_config(
                    binds=["{}:/data".format(dataset.path.path)],
                    port_bindings={http_port: http_port}),
                "ports": [http_port],
                "volumes": [u"/data"]}
            container = client.create_container(
                "python:2.7-slim",
                ["python", "-c", script.getContent()] + list(script_arguments),
                **docker_arguments)
            container_id = container["Id"]
            containers.insert(0, container_id)
            client.start(container=container_id)
            self.addCleanup(client.remove_container, container_id, force=True)
        starting_http_container = acquiring_lease.addCallback(
            start_http_container
        )

        def write_data(ignored):
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
        writing_data = starting_http_container.addCallback(write_data)

        def stop_container(ignored):
            """
            This ensures Docker hasn't got a lock on the volume that might
            prevent it being moved separate to the lock held by the lease.
            """
            [container_id] = containers
            client.stop(container_id)
        stopping_container = writing_data.addCallback(stop_container)

        def perform_operation(ignored):
            return operation(
                dataset_id=dataset_id, **additional_kwargs
            )
        performing_operation = stopping_container.addCallback(
            perform_operation
        )

        def wait_for_unexpected_umount(ignored):
            """
            If the dataset agent is broken and not respecting leases then we
            expect that 10 seconds is long enough for it to begin performing
            the requested operation.
            And the first step will always be to unmount the filesystem which
            should happen quickly since there are no open files and no Docker
            bind mounts to the filesystem.
            """
            return deferLater(reactor, 10, lambda: None)
        waiting = performing_operation.addCallback(wait_for_unexpected_umount)

        def restart_container(ignored):
            [container_id] = containers
            client.start(container=container_id)
        restarting_container = waiting.addCallback(
            restart_container
        )

        writing_data = restarting_container.addCallback(write_data)

        stopping_container = writing_data.addCallback(stop_container)

        def release_lease(ignored):
            return cluster.client.release_lease(dataset_id)
        releasing_lease = stopping_container.addCallback(release_lease)

        def wait_for_operation(ignored):
            """
            Now we've released the lease and stopped the running container, our
            earlier move / delete request should be enacted.
            """
            [dataset] = datasets
            return state_method(dataset)
        waiting_for_operation = releasing_lease.addCallback(wait_for_operation)

        return waiting_for_operation

    @require_moving_backend
    @require_cluster(2)
    def test_lease_prevents_move(self, cluster):
        """
        A dataset cannot be moved if a lease is held on it by a particular
        node.
        """
        return self._assert_lease_behavior(
            cluster=cluster,
            operation=cluster.client.move_dataset,
            additional_kwargs={'primary': cluster.nodes[1].uuid},
            state_method=cluster.wait_for_dataset,
        )

    @require_moving_backend
    @require_cluster(2)
    def test_lease_prevents_delete(self, cluster):
        """
        A dataset cannot be deleted if a lease is held on it by a particular
        node.
        """
        return self._assert_lease_behavior(
            cluster=cluster,
            operation=cluster.client.delete_dataset,
            additional_kwargs={},
            state_method=cluster.wait_for_deleted_dataset,
        )
