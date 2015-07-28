# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for the control service REST API.
"""

import socket
from contextlib import closing
from json import loads

from json import dumps

from twisted.trial.unittest import TestCase
from twisted.python.filepath import FilePath
from twisted.internet.defer import gatherResults

from treq import get, post, content

from eliot import Message

from ..testtools import (
    loop_until, random_name,
)
from .testtools import (
    require_cluster, require_moving_backend, create_dataset,
    create_python_container, REALISTIC_BLOCKDEVICE_SIZE,
)

CURRENT_DIRECTORY = FilePath(__file__).parent()


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
        d = create_python_container(
            self, cluster, {
                u"ports": [{u"internal": 8080, u"external": 8080}],
                u"node_uuid": cluster.nodes[0].uuid,
            }, CURRENT_DIRECTORY.child(b"hellohttp.py"))

        def check_result(response):
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
        If environment variables are specified when creating a container,
        those variables are available in the container's environment.
        """
        environment = {u"XBLOO": u"YBLAH", u"ZBLOO": u"ZEBRA"}

        d = create_python_container(
            self, cluster, {
                u"ports": [{u"internal": 8080, u"external": 8080}],
                u"node_uuid": cluster.nodes[0].uuid,
                u"environment": environment,
            }, CURRENT_DIRECTORY.child(b"envhttp.py"))

        def checked(_):
            host = cluster.nodes[0].public_address
            d = self.query_http_server(host, 8080)
            d.addCallback(lambda data: dict(loads(data)))
            return d
        d.addCallback(checked)

        d.addCallback(
            lambda response:
                self.assertDictContainsSubset(environment, response)
        )
        return d

    @require_moving_backend
    @require_cluster(2)
    def test_move_container_with_dataset(self, cluster):
        """
        Create a container with an attached dataset, issue API call
        to move the container. Wait until we can connect to the running
        container on the new host and verify the data has moved with it.
        """
        data = {u"the data": u"it moves"}
        post_data = {"data": dumps(data)}
        node1, node2 = cluster.nodes
        container_name = random_name(self)
        creating_dataset = create_dataset(self, cluster)

        def create_container(dataset):
            d = create_python_container(
                self, cluster, {
                    u"name": container_name,
                    u"ports": [{u"internal": 8080, u"external": 8080}],
                    u"node_uuid": node1.uuid,
                    u"volumes": [{u"dataset_id": dataset[u"dataset_id"],
                                  u"mountpoint": u"/data"}],
                }, CURRENT_DIRECTORY.child(b"datahttp.py"),
                additional_arguments=[u"/data"],
            )
            return d
        creating_dataset.addCallback(create_container)
        creating_dataset.addCallback(
            lambda _: self.post_http_server(
                node1.public_address, 8080, post_data)
        )

        def move_container(_):
            moved = cluster.move_container(
                container_name, node2.uuid
            )
            return moved
        creating_dataset.addCallback(move_container)
        creating_dataset.addCallback(
            lambda _: self.assert_http_server(
                node2.public_address, 8080,
                expected_response=post_data["data"])
        )

        return creating_dataset

    @require_cluster(1)
    def test_create_container_with_dataset(self, cluster):
        """
        Create a container with an attached dataset, write some data,
        shut it down, create a new container with same dataset, make sure
        the data is still there.
        """
        data = {u"the data": u"sample written data"}
        post_data = {"data": dumps(data)}
        node = cluster.nodes[0]
        container_name = random_name(self)
        creating_dataset = create_dataset(self, cluster)
        self.dataset_id = None

        def create_container(dataset):
            self.dataset_id = dataset[u"dataset_id"]
            d = create_python_container(
                self, cluster, {
                    u"name": container_name,
                    u"ports": [{u"internal": 8080, u"external": 8080}],
                    u"node_uuid": node.uuid,
                    u"volumes": [{u"dataset_id": self.dataset_id,
                                  u"mountpoint": u"/data"}],
                }, CURRENT_DIRECTORY.child(b"datahttp.py"),
                additional_arguments=[u"/data"],
                cleanup=False,
            )
            return d
        creating_dataset.addCallback(create_container)
        creating_dataset.addCallback(
            lambda _: self.post_http_server(
                node.public_address, 8080, post_data)
        )
        creating_dataset.addCallback(
            lambda _: self.assert_http_server(
                node.public_address, 8080,
                expected_response=post_data["data"])
        )
        creating_dataset.addCallback(
            lambda _: cluster.remove_container(container_name))

        def create_second_container(_):
            d = create_python_container(
                self, cluster, {
                    u"ports": [{u"internal": 8080, u"external": 8081}],
                    u"node_uuid": node.uuid,
                    u"volumes": [{u"dataset_id": self.dataset_id,
                                  u"mountpoint": u"/data"}],
                }, CURRENT_DIRECTORY.child(b"datahttp.py"),
                additional_arguments=[u"/data"],
            )
            return d
        creating_dataset.addCallback(create_second_container)
        creating_dataset.addCallback(
            lambda _: self.assert_http_server(
                node.public_address, 8081,
                expected_response=post_data["data"])
        )
        return creating_dataset

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

    def post_http_server(self, host, port, data, expected_response=b"ok"):
        """
        Make a POST request to an HTTP server on the given host and port
        and assert that the response body matches the expected response.

        :param bytes host: Host to connect to.
        :param int port: Port to connect to.
        :param bytes data: The raw request body data.
        :param bytes expected_response: The HTTP response body expected.
            Defaults to b"ok"
        """
        def make_post(host, port, data):
            request = post(
                "http://{host}:{port}".format(host=host, port=port),
                data=data,
                persistent=False
            )

            def failed(failure):
                Message.new(message_type=u"acceptance:http_query_failed",
                            reason=unicode(failure)).write()
                return False
            request.addCallbacks(content, failed)
            return request
        d = verify_socket(host, port)
        d.addCallback(lambda _: loop_until(lambda: make_post(
            host, port, data)))
        d.addCallback(self.assertEqual, expected_response)
        return d

    def query_http_server(self, host, port, path=b""):
        """
        Return the response from a HTTP server.

        We try multiple since it may take a little time for the HTTP
        server to start up.

        :param bytes host: Host to connect to.
        :param int port: Port to connect to.
        :param bytes path: Optional path and query string.

        :return: ``Deferred`` that fires with the body of the response.
        """
        def query():
            req = get(
                "http://{host}:{port}{path}".format(
                    host=host, port=port, path=path),
                persistent=False
            )

            def failed(failure):
                Message.new(message_type=u"acceptance:http_query_failed",
                            reason=unicode(failure)).write()
                return False
            req.addCallbacks(content, failed)
            return req

        d = verify_socket(host, port)
        d.addCallback(lambda _: loop_until(query))
        return d

    def assert_http_server(self, host, port,
                           path=b"", expected_response=b"hi"):

        """
        Assert that a HTTP serving a response with body ``b"hi"`` is running
        at given host and port.

        This can be coupled with code that only conditionally starts up
        the HTTP server via Flocker in order to check if that particular
        setup succeeded.

        :param bytes host: Host to connect to.
        :param int port: Port to connect to.
        :param bytes path: Optional path and query string.
        :param bytes expected_response: The HTTP response body expected.
            Defaults to b"hi"

        :return: ``Deferred`` that fires when assertion has run.
        """
        d = self.query_http_server(host, port, path)
        d.addCallback(self.assertEqual, expected_response)
        return d

    @require_cluster(1)
    def test_non_root_container_can_access_dataset(self, cluster):
        """
        A container running as a user that is not root can write to a
        dataset attached as a volume.
        """
        node = cluster.nodes[0]
        creating_dataset = create_dataset(self, cluster)

        def created_dataset(dataset):
            return create_python_container(
                self, cluster, {
                    u"ports": [{u"internal": 8080, u"external": 8080}],
                    u"node_uuid": node.uuid,
                    u"volumes": [{u"dataset_id": dataset[u"dataset_id"],
                                  u"mountpoint": u"/data"}],
                }, CURRENT_DIRECTORY.child(b"nonrootwritehttp.py"),
                additional_arguments=[u"/data"])
        creating_dataset.addCallback(created_dataset)

        creating_dataset.addCallback(
            lambda _: self.assert_http_server(node.public_address, 8080))
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
        destination_port = 8080
        origin_port = 8081

        [destination, origin] = cluster.nodes

        running = gatherResults([
            create_python_container(
                self, cluster, {
                    u"ports": [{u"internal": 8080,
                                u"external": destination_port}],
                    u"node_uuid": destination.uuid,
                }, CURRENT_DIRECTORY.child(b"hellohttp.py")),
            create_python_container(
                self, cluster, {
                    u"ports": [{u"internal": 8081,
                                u"external": origin_port}],
                    u"links": [{u"alias": "dest", u"local_port": 80,
                                u"remote_port": destination_port}],
                    u"node_uuid": origin.uuid,
                }, CURRENT_DIRECTORY.child(b"proxyhttp.py")),
            # Wait for the link target container to be accepting connections.
            verify_socket(destination.public_address, destination_port),
            # Wait for the link source container to be accepting connections.
            verify_socket(origin.public_address, origin_port),
            ])

        running.addCallback(
            lambda _: self.assert_http_server(
                origin.public_address, origin_port))
        return running

    @require_cluster(2)
    def test_traffic_routed(self, cluster):
        """
        An application can be accessed even from a connection to a node
        which it is not running on.
        """
        port = 8080

        [destination, origin] = cluster.nodes

        running = gatherResults([
            create_python_container(
                self, cluster, {
                    u"ports": [{u"internal": 8080, u"external": port}],
                    u"node_uuid": destination.uuid,
                }, CURRENT_DIRECTORY.child(b"hellohttp.py")),
            # Wait for the destination to be accepting connections.
            verify_socket(destination.public_address, port),
            # Wait for the origin container to be accepting connections.
            verify_socket(origin.public_address, port),
            ])

        running.addCallback(
            # Connect to the machine where the container is NOT running:
            lambda _: self.assert_http_server(origin.public_address, port))
        return running


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

        All attributes, including the maximum size, are preserved.
        """
        waiting_for_create = create_dataset(
            self, cluster, maximum_size=REALISTIC_BLOCKDEVICE_SIZE)

        # Once created, request to move the dataset to node2
        def move_dataset(dataset):
            dataset_moving = cluster.update_dataset(
                dataset['dataset_id'], {
                    u'primary': cluster.nodes[1].uuid
                })

            # Wait for the dataset to be moved; we expect the state to
            # match that of the originally created dataset in all ways
            # other than the location.
            moved_dataset = dataset.copy()
            moved_dataset[u'primary'] = cluster.nodes[1].uuid
            dataset_moving.addCallback(
                lambda dataset: cluster.wait_for_dataset(dataset))
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
