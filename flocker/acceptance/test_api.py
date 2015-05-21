# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for the control service REST API.
"""

import socket

from uuid import uuid4

from twisted.trial.unittest import TestCase

from twisted.internet import reactor

from treq import get, json_content

from ..testtools import REALISTIC_BLOCKDEVICE_SIZE, loop_until, random_name
from .testtools import (
    MONGO_IMAGE, require_mongo, get_mongo_client,
    get_test_cluster, require_cluster,
    require_moving_backend,
)


def verify_socket(host, port):
    """
    Wait until the destionation can be connected to.

    :param bytes host: Host to connect to.
    :param int port: Port to connect to.

    :return Deferred: Firing when connection is possible.
    """
    def can_connect():
        s = socket.socket()
        conn = s.connect_ex((host, port))
        return False if conn else True

    dl = loop_until(can_connect)
    return dl


class ContainerAPITests(TestCase):
    """
    Tests for the container API.
    """
    def _create_container(self):
        """
        Create a container listening on port 8080.

        :return: ``Deferred`` firing with a tuple of ``Cluster`` instance
        and container dictionary once the container is up and running.
        """
        data = {
            u"name": random_name(self),
            u"image": "clusterhq/flask:latest",
            u"ports": [{u"internal": 80, u"external": 8080}],
            u'restart_policy': {u'name': u'never'}
        }
        waiting_for_cluster = get_test_cluster(reactor, node_count=1)

        def create_container(cluster, data):
            data[u"node_uuid"] = cluster.nodes[0].uuid
            return cluster.create_container(data)

        d = waiting_for_cluster.addCallback(create_container, data)

        def check_result(result):
            cluster, response = result
            self.addCleanup(cluster.remove_container, data[u"name"])

            self.assertEqual(response, data)
            dl = verify_socket(cluster.nodes[0].address, 8080)
            dl.addCallback(lambda _: (cluster, response))
            return dl

        d.addCallback(check_result)
        return d

    @require_cluster(1)
    def test_create_container_with_ports(self, cluster):
        """
        Create a container including port mappings on a single-node cluster.
        """
        return self._create_container()

    @require_cluster(1)
    def test_create_container_with_environment(self, cluster):
        """
        Create a container including environment variables on a single-node
        cluster.
        """
        data = {
            u"name": random_name(self),
            u"image": "clusterhq/flaskenv:latest",
            u"ports": [{u"internal": 8080, u"external": 8081}],
            u"environment": {u"ACCEPTANCE_ENV_LABEL": 'acceptance test ok'},
            u'restart_policy': {u'name': u'never'},
        }
        waiting_for_cluster = get_test_cluster(reactor, node_count=1)

        def create_container(cluster, data):
            data[u"node_uuid"] = cluster.nodes[0].uuid
            return cluster.create_container(data)

        d = waiting_for_cluster.addCallback(create_container, data)

        def check_result((cluster, response)):
            self.addCleanup(cluster.remove_container, data[u"name"])
            self.assertEqual(response, data)
            return cluster

        def query_environment(host, port):
            """
            The running container, clusterhq/flaskenv, is a simple Flask app
            that returns a JSON dump of the container's environment, so we
            make an HTTP request and parse the response.
            """
            req = get(
                "http://{host}:{port}".format(host=host, port=port),
                persistent=False
            ).addCallback(json_content)
            return req

        d.addCallback(check_result)

        def checked(cluster):
            host = cluster.nodes[0].address
            d = verify_socket(host, 8081)
            d.addCallback(lambda _: query_environment(host, 8081))
            return d
        d.addCallback(checked)

        d.addCallback(
            lambda response:
                self.assertDictContainsSubset(data[u"environment"], response)
        )
        return d

    @require_moving_backend
    @require_mongo
    @require_cluster(2)
    def test_move_container_with_dataset(self, cluster):
        """
        Create a mongodb container with an attached dataset, issue API call
        to move the container. Wait until we can connect to the running
        container on the new host and verify the data has moved with it.
        """
        creating_dataset = create_dataset(self, nodes=2)

        def created_dataset(result):
            cluster, dataset = result
            mongodb = {
                u"name": random_name(self),
                u"node_uuid": cluster.nodes[0].uuid,
                u"image": MONGO_IMAGE,
                u"ports": [{u"internal": 27017, u"external": 27017}],
                u'restart_policy': {u'name': u'never'},
                u"volumes": [{u"dataset_id": dataset[u"dataset_id"],
                              u"mountpoint": u"/data/db"}],
            }
            created = cluster.create_container(mongodb)
            created.addCallback(lambda _: self.addCleanup(
                cluster.remove_container, mongodb[u"name"]))
            created.addCallback(
                lambda _: get_mongo_client(cluster.nodes[0].address))

            def got_mongo_client(client):
                database = client.example
                database.posts.insert({u"the data": u"it moves"})
                return database.posts.find_one()
            created.addCallback(got_mongo_client)

            def inserted(record):
                moved = cluster.move_container(
                    mongodb[u"name"], cluster.nodes[1].uuid
                )

                def destroy_and_recreate(_, record):
                    """
                    After moving our container via the API, we then remove the
                    container on the new host and recreate it, pointing to the
                    same dataset, but with the new container instance exposing
                    a different external port. This technique ensures that the
                    test does not pass by mere accident without the container
                    having moved; by recreating the container on its new host
                    after moving, we can be sure that if we can still connect
                    and read the data, the dataset was successfully moved along
                    with the container.
                    """
                    removed = cluster.remove_container(mongodb[u"name"])
                    mongodb2 = mongodb.copy()
                    mongodb2[u"ports"] = [
                        {u"internal": 27017, u"external": 27018}
                    ]
                    mongodb2[u"node_uuid"] = cluster.nodes[1].uuid
                    removed.addCallback(
                        lambda _: cluster.create_container(mongodb2))
                    removed.addCallback(lambda _: record)
                    return removed
                moved.addCallback(destroy_and_recreate, record)
                return moved
            created.addCallback(inserted)

            def moved(record):
                d = get_mongo_client(cluster.nodes[1].address, 27018)
                d.addCallback(lambda client: client.example.posts.find_one())
                d.addCallback(self.assertEqual, record)
                return d

            created.addCallback(moved)
            return created
        creating_dataset.addCallback(created_dataset)
        return creating_dataset

    @require_mongo
    @require_cluster(1)
    def test_create_container_with_dataset(self, cluster):
        """
        Create a mongodb container with an attached dataset, insert some data,
        shut it down, create a new container with same dataset, make sure
        the data is still there.
        """
        creating_dataset = create_dataset(self)

        def created_dataset(result):
            cluster, dataset = result
            mongodb = {
                u"name": random_name(self),
                u"node_uuid": cluster.nodes[0].uuid,
                u"image": MONGO_IMAGE,
                u"ports": [{u"internal": 27017, u"external": 27017}],
                u'restart_policy': {u'name': u'never'},
                u"volumes": [{u"dataset_id": dataset[u"dataset_id"],
                              u"mountpoint": u"/data/db"}],
            }
            created = cluster.create_container(mongodb)
            created.addCallback(lambda _: self.addCleanup(
                cluster.remove_container, mongodb[u"name"]))
            created.addCallback(
                lambda _: get_mongo_client(cluster.nodes[0].address))

            def got_mongo_client(client):
                database = client.example
                database.posts.insert({u"the data": u"it moves"})
                return database.posts.find_one()
            created.addCallback(got_mongo_client)

            def inserted(record):
                removed = cluster.remove_container(mongodb[u"name"])
                mongodb2 = mongodb.copy()
                mongodb2[u"ports"] = [{u"internal": 27017, u"external": 27018}]
                removed.addCallback(
                    lambda _: cluster.create_container(mongodb2))
                removed.addCallback(lambda _: record)
                return removed
            created.addCallback(inserted)

            def restarted(record):
                d = get_mongo_client(cluster.nodes[0].address, 27018)
                d.addCallback(lambda client: client.example.posts.find_one())
                d.addCallback(self.assertEqual, record)
                return d
            created.addCallback(restarted)
            return created
        creating_dataset.addCallback(created_dataset)
        return creating_dataset

    @require_cluster(1)
    def test_current(self, cluster):
        """
        The current container endpoint includes a currently running container.
        """
        creating = self._create_container()

        def created(result):
            cluster, data = result
            data[u"running"] = True
            data[u"host"] = cluster.nodes[0].address

            def in_current():
                current = cluster.current_containers()
                current.addCallback(lambda result: data in result[1])
                return current
            return loop_until(in_current)
        creating.addCallback(created)
        return creating


def create_dataset(test_case, nodes=1,
                   maximum_size=REALISTIC_BLOCKDEVICE_SIZE):
    """
    Create a dataset on a cluster.

    :param TestCase test_case: The test the API is running on.
    :param int nodes: The number of nodes to create. Defaults to 1.
    :param int maximum_size: The size of the dataset to create on the test
        cluster.
    :return: ``Deferred`` firing with a tuple of (``Cluster``
        instance, dataset dictionary) once the dataset is present in
        actual cluster state.
    """
    # Create a cluster
    waiting_for_cluster = get_test_cluster(reactor, node_count=nodes)

    # Configure a dataset on node1
    def configure_dataset(cluster):
        """
        Send a dataset creation request on node1.
        """
        requested_dataset = {
            u"primary": cluster.nodes[0].uuid,
            u"dataset_id": unicode(uuid4()),
            u"maximum_size": maximum_size,
            u"metadata": {u"name": u"my_volume"},
        }

        d = cluster.create_dataset(requested_dataset)

        def got_result(result):
            test_case.addCleanup(
                cluster.delete_dataset, requested_dataset[u"dataset_id"])
            return result
        d.addCallback(got_result)
        return d

    configuring_dataset = waiting_for_cluster.addCallback(
        configure_dataset
    )

    # Wait for the dataset to be created
    waiting_for_create = configuring_dataset.addCallback(
        lambda (cluster, dataset): cluster.wait_for_dataset(dataset)
    )

    return waiting_for_create


class DatasetAPITests(TestCase):
    """
    Tests for the dataset API.
    """
    def test_dataset_creation(self):
        """
        A dataset can be created on a specific node.
        """
        return create_dataset(self)

    @require_moving_backend
    def test_dataset_move(self):
        """
        A dataset can be moved from one node to another.
        """
        # Create a 2 node cluster
        waiting_for_cluster = get_test_cluster(reactor, node_count=2)

        # Configure a dataset on node1
        def configure_dataset(cluster):
            """
            Send a dataset creation request on node1.
            """
            requested_dataset = {
                u"primary": cluster.nodes[0].uuid,
                u"dataset_id": unicode(uuid4()),
                u"metadata": {u"name": u"my_volume"}
            }

            return cluster.create_dataset(requested_dataset)
        configuring_dataset = waiting_for_cluster.addCallback(
            configure_dataset
        )

        # Wait for the dataset to be created
        waiting_for_create = configuring_dataset.addCallback(
            lambda (cluster, dataset): cluster.wait_for_dataset(dataset)
        )

        # Once created, request to move the dataset to node2
        def move_dataset((cluster, dataset)):
            moved_dataset = {
                u'primary': cluster.nodes[1].uuid
            }
            return cluster.update_dataset(dataset['dataset_id'], moved_dataset)
        dataset_moving = waiting_for_create.addCallback(move_dataset)

        # Wait for the dataset to be moved
        waiting_for_move = dataset_moving.addCallback(
            lambda (cluster, dataset): cluster.wait_for_dataset(dataset)
        )

        return waiting_for_move

    def test_dataset_deletion(self):
        """
        A dataset can be deleted, resulting in its removal from the node.
        """
        created = create_dataset(self)

        def delete_dataset(result):
            cluster, dataset = result
            deleted = cluster.delete_dataset(dataset["dataset_id"])

            def not_exists():
                request = cluster.datasets_state()
                request.addCallback(
                    lambda actual_datasets: dataset["dataset_id"] not in
                    (d["dataset_id"] for d in actual_datasets))
                return request
            deleted.addCallback(lambda _: loop_until(not_exists))
            return deleted
        created.addCallback(delete_dataset)
        return created
