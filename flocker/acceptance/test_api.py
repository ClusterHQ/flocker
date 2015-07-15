# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for the control service REST API.
"""

import socket
from contextlib import closing
from uuid import uuid4

from pyrsistent import thaw, pmap

from twisted.trial.unittest import TestCase

from twisted.internet.defer import gatherResults

from treq import get, json_content, content

from eliot import Message

from ..testtools import (
    REALISTIC_BLOCKDEVICE_SIZE, loop_until, random_name, find_free_port,
)
from .testtools import (
    MONGO_IMAGE, require_mongo, get_mongo_client,
    require_cluster, require_moving_backend,
)

# A command that will run an "HTTP" in a Busybox container.  The server
# responds "hi" to any request.
BUSYBOX_HTTP = [
    u"sh", u"-c",
    u"""\
echo -n '#!/bin/sh
echo -n "HTTP/1.1 200 OK\r\n\r\nhi"
' > /tmp/script.sh;
chmod +x /tmp/script.sh;
nc -ll -p 8080 -e /tmp/script.sh
"""
]


def verify_socket(host, port):
    """
    Wait until the destionation can be connected to.

    :param bytes host: Host to connect to.
    :param int port: Port to connect to.

    :return Deferred: Firing when connection is possible.
    """
    def can_connect():
        with closing(socket.socket()) as s:
            conn = s.connect_ex((host, port))
            Message.new(
                message_type="acceptance:verify_socket",
                host=host,
                port=port,
                result=conn,
            ).write()
            return conn == 0

    dl = loop_until(can_connect)
    return dl


class ContainerAPITests(TestCase):
    """
    Tests for the container API.
    """
    def _create_container(self, cluster):
        """
        Create a container listening on port 8080.

        :return: ``Deferred`` firing with a container dictionary once the
            container is up and running.
        """
        data = {
            u"name": random_name(self),
            u"image": "clusterhq/flask:latest",
            u"ports": [{u"internal": 80, u"external": 8080}],
            u'restart_policy': {u'name': u'never'},
            u"node_uuid": cluster.nodes[0].uuid,
        }

        d = cluster.create_container(data)

        def check_result(response):
            self.addCleanup(cluster.remove_container, data[u"name"])

            self.assertEqual(response, data)
            dl = verify_socket(cluster.nodes[0].public_address, 8080)
            dl.addCallback(lambda _: response)
            return dl

        d.addCallback(check_result)
        return d

    @require_cluster(1)
    def test_create_container_with_ports(self, cluster):
        """
        Create a container including port mappings on a single-node cluster.
        """
        return self._create_container(cluster)

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

        data[u"node_uuid"] = cluster.nodes[0].uuid
        d = cluster.create_container(data)

        def check_result(response):
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
            host = cluster.nodes[0].public_address
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
        creating_dataset = create_dataset(self, cluster)

        def created_dataset(dataset):
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
                lambda _: get_mongo_client(cluster.nodes[0].public_address))

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
                d = get_mongo_client(cluster.nodes[1].public_address, 27018)
                d.addCallback(lambda client: client.example.posts.find_one())
                d.addCallback(self.assertEqual, record)
                return d

            created.addCallback(moved)
            return created
        creating_dataset.addCallback(created_dataset)
        return creating_dataset
    # FLOC-2488 This test has been measured to take longer than the default
    # trial timeout (120s), on AWS, using AWS dataset backend and on Vagrant
    # using the ZFS backend.
    test_move_container_with_dataset.timeout = 480

    @require_mongo
    @require_cluster(1)
    def test_create_container_with_dataset(self, cluster):
        """
        Create a mongodb container with an attached dataset, insert some data,
        shut it down, create a new container with same dataset, make sure
        the data is still there.
        """
        creating_dataset = create_dataset(self, cluster)

        def created_dataset(dataset):
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
                lambda _: get_mongo_client(cluster.nodes[0].public_address))

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
                d = get_mongo_client(cluster.nodes[0].public_address, 27018)
                d.addCallback(lambda client: client.example.posts.find_one())
                d.addCallback(self.assertEqual, record)
                return d
            created.addCallback(restarted)
            return created
        creating_dataset.addCallback(created_dataset)
        return creating_dataset
    # FLOC-2488 This test has been measured to take longer than the default
    # trial timeout (120s), on AWS, using AWS dataset backend and on Vagrant
    # using the ZFS backend.
    test_create_container_with_dataset.timeout = 480

    @require_cluster(1)
    def test_current(self, cluster):
        """
        The current container endpoint includes a currently running container.
        """
        creating = self._create_container(cluster)

        def created(data):
            data[u"running"] = True

            def in_current():
                current = cluster.current_containers()
                current.addCallback(lambda result: data in result)
                return current
            return loop_until(in_current)
        creating.addCallback(created)
        return creating

    def assert_busybox_http(self, host, port):
        """
        Assert that a HTTP serving a response with body ``b"hi"`` is running
        at given host and port.

        This can be coupled with code that only conditionally starts up
        the HTTP server via Flocker in order to check if that particular
        setup succeeded.

        :param bytes host: Host to connect to.
        :param int port: Port to connect to.
        """
        def query(host, port):
            req = get(
                "http://{host}:{port}".format(host=host, port=port),
                persistent=False
            ).addCallback(content)
            return req

        d = verify_socket(host, port)
        d.addCallback(lambda _: query(host, port))
        d.addCallback(self.assertEqual, b"hi")
        return d

    @require_cluster(1)
    def test_non_root_container_can_access_dataset(self, cluster):
        """
        A container running as a user that is not root can write to a
        dataset attached as a volume.
        """
        _, port = find_free_port()
        node = cluster.nodes[0]
        container = {
            u"name": random_name(self),
            u"node_uuid": node.uuid,
            u"image": u"busybox",
            u"ports": [{u"internal": 8080, u"external": port}],
            u'restart_policy': {u'name': u'never'},
            u"volumes": [{u"dataset_id": None,
                          u"mountpoint": u"/data"}],
            u"command_line": [
                # Run as non-root user:
                u"su", u"-", u"nobody", u"-c", u"sh", u"-c",
                # Write something to volume we attached, and then
                # expose what we wrote as a web server; for info on nc options
                # you can do `docker run busybox man nc`.
                u"""\
echo -n '#!/bin/sh
echo -n "HTTP/1.1 200 OK\r\n\r\nhi"
' > /data/script.sh;
chmod +x /data/script.sh;
nc -ll -p 8080 -e /data/script.sh
            """]}

        creating_dataset = create_dataset(self, cluster)

        def created_dataset(dataset):
            container[u"volumes"][0][u"dataset_id"] = dataset[u"dataset_id"]
            return cluster.create_container(container)
        creating_dataset.addCallback(created_dataset)

        creating_dataset.addCallback(lambda _: self.addCleanup(
            cluster.remove_container, container[u"name"]))
        creating_dataset.addCallback(
            lambda _: self.assert_busybox_http(node.public_address, port))
        return creating_dataset

    @require_cluster(2)
    def test_linking(self, cluster):
        """
        A link from an origin container to a destination container allows the
        origin container to establish connections to the destination container
        when the containers are running on different machines using an address
        obtained from ``<ALIAS>_PORT_<PORT>_TCP_{ADDR,PORT}``-style environment
        set in the origin container's environment.
        """
        _, destination_port = find_free_port()
        _, origin_port = find_free_port()

        [destination, origin] = cluster.nodes

        busybox = pmap({
            u"image": u"busybox",
        })

        destination_container = busybox.update({
            u"name": random_name(self),
            u"node_uuid": destination.uuid,
            u"ports": [{u"internal": 8080, u"external": destination_port}],
            u"command_line": BUSYBOX_HTTP,
        })
        self.addCleanup(
            cluster.remove_container, destination_container[u"name"]
        )

        origin_container = busybox.update({
            u"name": random_name(self),
            u"node_uuid": origin.uuid,
            u"links": [{u"alias": "DEST", u"local_port": 80,
                        u"remote_port": destination_port}],
            u"ports": [{u"internal": 9000, u"external": origin_port}],
            u"command_line": [
                u"sh", u"-c", u"""\
echo -n '#!/bin/sh
nc $DEST_PORT_80_TCP_ADDR $DEST_PORT_80_TCP_PORT
' > /tmp/script.sh;
chmod +x /tmp/script.sh;
nc -ll -p 9000 -e /tmp/script.sh
                """]})
        self.addCleanup(
            cluster.remove_container, origin_container[u"name"]
        )
        running = gatherResults([
            cluster.create_container(thaw(destination_container)),
            cluster.create_container(thaw(origin_container)),
            # Wait for the link target container to be accepting connections.
            verify_socket(destination.public_address, destination_port),
            # Wait for the link source container to be accepting connections.
            verify_socket(origin.public_address, origin_port),
        ])

        running.addCallback(
            lambda _: self.assert_busybox_http(
                origin.public_address, origin_port))
        return running


def create_dataset(test_case, cluster,
                   maximum_size=REALISTIC_BLOCKDEVICE_SIZE):
    """
    Create a dataset on a cluster (on its first node, specifically).

    :param TestCase test_case: The test the API is running on.
    :param Cluster cluster: The test ``Cluster``.
    :param int maximum_size: The size of the dataset to create on the test
        cluster.
    :return: ``Deferred`` firing with a tuple of (``Cluster``
        instance, dataset dictionary) once the dataset is present in
        actual cluster state.
    """
    # Configure a dataset on node1
    requested_dataset = {
        u"primary": cluster.nodes[0].uuid,
        u"dataset_id": unicode(uuid4()),
        u"maximum_size": maximum_size,
        u"metadata": {u"name": u"my_volume"},
    }

    configuring_dataset = cluster.create_dataset(requested_dataset)

    # Wait for the dataset to be created
    waiting_for_create = configuring_dataset.addCallback(
        lambda dataset: cluster.wait_for_dataset(dataset)
    )

    return waiting_for_create


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

    @require_moving_backend
    @require_cluster(2)
    def test_dataset_move(self, cluster):
        """
        A dataset can be moved from one node to another.
        """
        waiting_for_create = create_dataset(self, cluster)

        # Once created, request to move the dataset to node2
        def move_dataset(dataset):
            moved_dataset = {
                u'primary': cluster.nodes[1].uuid
            }
            return cluster.update_dataset(dataset['dataset_id'], moved_dataset)
        dataset_moving = waiting_for_create.addCallback(move_dataset)

        # Wait for the dataset to be moved
        waiting_for_move = dataset_moving.addCallback(
            lambda dataset: cluster.wait_for_dataset(dataset)
        )

        return waiting_for_move

    @require_cluster(1)
    def test_dataset_deletion(self, cluster):
        """
        A dataset can be deleted, resulting in its removal from the node.
        """
        created = create_dataset(self, cluster)

        def delete_dataset(dataset):
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
