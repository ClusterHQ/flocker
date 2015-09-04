# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for the datasets REST API.
"""

from uuid import UUID, uuid4

from twisted.internet.task import deferLater
from twisted.trial.unittest import TestCase
from twisted.internet import reactor

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
        http_port = 8080
        dataset_id = uuid4()
        dataset_path = []
        client = get_docker_client(cluster, cluster.nodes[0].public_address)
        d = create_dataset(
            self, cluster, maximum_size=REALISTIC_BLOCKDEVICE_SIZE,
            dataset_id=dataset_id
        )

        def acquire_lease(dataset):
            # Call the API to acquire a lease with the dataset ID.
            acquiring_lease = cluster.client.acquire_lease(
                dataset.dataset_id, UUID(cluster.nodes[0].uuid), expires=1000)

            def get_dataset_path(lease, created_dataset):
                getting_datasets = cluster.client.list_datasets_state()

                def extract_dataset_path(datasets):
                    dataset_path.insert(0, datasets[0].path)
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
            # import pdb;pdb.set_trace()
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
            primary = cluster.nodes[1].uuid
            # This ensures Docker hasn't got a lock on the volume that
            # might prevent it being moved separate to the lock held by
            # the lease.
            client.stop(container_id)
            move_dataset_request = cluster.client.move_dataset(
                primary, dataset_id)
            move_dataset_request.addCallback(lambda _: container_id)
            return move_dataset_request

        d.addCallback(stop_container, client, dataset_id)

        def wait_five_seconds(container_id):
            return deferLater(reactor, 10, lambda: container_id)

        d.addCallback(wait_five_seconds)

        def restart_container(container_id, client, cluster):
            client.start(container=container_id)
            return container_id

        d.addCallback(restart_container, client, cluster)

        d.addCallback(write_data)

        def stop_container_again(container_id, client, dataset_id):
            client.stop(container_id)
            releasing = cluster.client.release_lease(dataset_id)
            releasing.addCallback(lambda _: container_id)
            return releasing

        d.addCallback(stop_container_again, client, dataset_id)

        d.addCallback(wait_five_seconds)

        # d.addCallback(restart_container, client, cluster)

        d.addCallback(lambda _: start_http_container(dataset_path[0], client))

        def container_did_start(container_id):
            check_datasets_config = cluster.client.list_datasets_configuration()
            def got_datasets_config(datasets):
                #ncluster = cluster
                #import pdb;pdb.set_trace()
                get_ds_state = cluster.client.list_datasets_state()
                def got_ds_state(state_datasets):
                    config_datasets = datasets
                    ncluster = cluster
                    # import pdb;pdb.set_trace()
                get_ds_state.addCallback(got_ds_state)
                return get_ds_state
            check_datasets_config.addCallback(got_datasets_config)
            #import pdb;pdb.set_trace()
            #self.fail("The container didn't fail to start :'(")
            return check_datasets_config

        def container_no_start(some_failure):
            # import pdb;pdb.set_trace()
            pass

        d.addCallback(container_did_start)
        d.addErrback(container_no_start)

        return d

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
