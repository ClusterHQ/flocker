# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for the control service REST API.
"""

from os import environ
import socket

from uuid import uuid4
from json import dumps

from twisted.internet.defer import succeed
from twisted.trial.unittest import TestCase
from twisted.web.http import OK, CREATED, BAD_REQUEST

from unittest import SkipTest
from treq import get, post, delete, json_content
from pyrsistent import PRecord, field, CheckedPVector

from ..testtools import REALISTIC_BLOCKDEVICE_SIZE, loop_until, random_name
from .testtools import (
    MONGO_IMAGE, require_mongo, get_mongo_client,
)
from ..control.httpapi import REST_API_PORT


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


class Node(PRecord):
    """
    A record of a cluster node.

    :ivar bytes address: The IPv4 address of the node.
    """
    address = field(type=bytes)


class _NodeList(CheckedPVector):
    """
    A list of nodes.

    See https://github.com/tobgu/pyrsistent/issues/26 for more succinct
    idiom combining this with ``field()``.
    """
    __type__ = Node


def check_and_decode_json(result, response_code):
    """
    Given ``treq`` response object, extract JSON and ensure response code
    is the expected one.

    :param result: ``treq`` response.
    :param int response_code: Expected response code.

    :return: ``Deferred`` firing with decoded JSON.
    """
    if result.code != response_code:
        raise ValueError("Unexpected response code:", result.code)
    return json_content(result)


class Cluster(PRecord):
    """
    A record of the control service and the nodes in a cluster for acceptance
    testing.

    :param Node control_node: The node running the ``flocker-control``
        service.
    :param list nodes: The ``Node`` s in this cluster.
    """
    control_node = field(type=Node)
    nodes = field(type=_NodeList)

    @property
    def base_url(self):
        """
        :returns: The base url for API requests to this cluster's control
            service.
        """
        return b"http://{}:{}/v1".format(
            self.control_node.address, REST_API_PORT
        )

    def datasets_state(self):
        """
        Return the actual dataset state of the cluster.

        :return: ``Deferred`` firing with a list of dataset dictionaries,
            the state of the cluster.
        """
        request = get(self.base_url + b"/state/datasets", persistent=False)
        request.addCallback(check_and_decode_json, OK)
        return request

    def wait_for_dataset(self, dataset_properties):
        """
        Poll the dataset state API until the supplied dataset exists.

        :param dict dataset_properties: The attributes of the dataset that
            we're waiting for.
        :returns: A ``Deferred`` which fires with a 2-tuple of ``Cluster`` and
            API response when a dataset with the supplied properties appears in
            the cluster.
        """
        def created():
            """
            Check the dataset state list for the expected dataset.
            """
            request = self.datasets_state()

            def got_body(body):
                # State listing doesn't have metadata or deleted, but does
                # have unpredictable path.
                expected_dataset = dataset_properties.copy()
                del expected_dataset[u"metadata"]
                del expected_dataset[u"deleted"]
                for dataset in body:
                    dataset.pop("path")
                return expected_dataset in body
            request.addCallback(got_body)
            return request

        waiting = loop_until(created)
        waiting.addCallback(lambda ignored: (self, dataset_properties))
        return waiting

    def create_dataset(self, dataset_properties):
        """
        Create a dataset with the supplied ``dataset_properties``.

        :param dict dataset_properties: The properties of the dataset to
            create.
        :returns: A ``Deferred`` which fires with a 2-tuple of ``Cluster`` and
            API response when a dataset with the supplied properties has been
            persisted to the cluster configuration.
        """
        request = post(
            self.base_url + b"/configuration/datasets",
            data=dumps(dataset_properties),
            headers={b"content-type": b"application/json"},
            persistent=False
        )

        request.addCallback(check_and_decode_json, CREATED)
        # Return cluster and API response
        request.addCallback(lambda response: (self, response))
        return request

    def update_dataset(self, dataset_id, dataset_properties):
        """
        Update a dataset with the supplied ``dataset_properties``.

        :param unicode dataset_id: The uuid of the dataset to be modified.
        :param dict dataset_properties: The properties of the dataset to
            create.
        :returns: A 2-tuple of (cluster, api_response)
        """
        request = post(
            self.base_url + b"/configuration/datasets/%s" % (
                dataset_id.encode('ascii'),
            ),
            data=dumps(dataset_properties),
            headers={b"content-type": b"application/json"},
            persistent=False
        )

        request.addCallback(check_and_decode_json, OK)
        # Return cluster and API response
        request.addCallback(lambda response: (self, response))
        return request

    def delete_dataset(self, dataset_id):
        """
        Delete a dataset.

        :param unicode dataset_id: The uuid of the dataset to be modified.

        :returns: A 2-tuple of (cluster, api_response)
        """
        request = delete(
            self.base_url + b"/configuration/datasets/%s" % (
                dataset_id.encode('ascii'),
            ),
            headers={b"content-type": b"application/json"},
            persistent=False
        )

        request.addCallback(check_and_decode_json, OK)
        # Return cluster and API response
        request.addCallback(lambda response: (self, response))
        return request

    def create_container(self, properties):
        """
        Create a container with the specified properties.

        :param dict properties: A ``dict`` mapping to the API request fields
            to create a container.

        :returns: A tuple of (cluster, api_response)
        """
        request = post(
            self.base_url + b"/configuration/containers",
            data=dumps(properties),
            headers={b"content-type": b"application/json"},
            persistent=False
        )

        request.addCallback(check_and_decode_json, CREATED)
        request.addCallback(lambda response: (self, response))
        return request

    def move_container(self, name, host):
        """
        Move a container.

        :param unicode name: The name of the container to move.

        :param unicode host: The host to which the container should be moved.

        :returns: A tuple of (cluster, api_response)
        """
        request = post(
            self.base_url + b"/configuration/containers/" +
            name.encode("ascii"),
            data=dumps({u"host": host}),
            headers={b"content-type": b"application/json"},
            persistent=False
        )

        request.addCallback(check_and_decode_json, OK)
        request.addCallback(lambda response: (self, response))
        return request

    def remove_container(self, name):
        """
        Remove a container.

        :param unicode name: The name of the container to remove.

        :returns: A tuple of (cluster, api_response)
        """
        request = delete(
            self.base_url + b"/configuration/containers/" +
            name.encode("ascii"),
            persistent=False
        )

        request.addCallback(check_and_decode_json, OK)
        request.addCallback(lambda response: (self, response))
        return request

    def current_containers(self):
        """
        Get current containers.

        :return: A ``Deferred`` firing with a tuple (cluster instance, API
            response).
        """
        request = get(
            self.base_url + b"/state/containers",
            persistent=False
        )

        request.addCallback(check_and_decode_json, OK)
        request.addCallback(lambda response: (self, response))
        return request


def get_test_cluster(test_case, node_count):
    """
    Build a ``Cluster`` instance with at least ``node_count`` nodes.

    :param TestCase test_case: The test case instance on which to register
        cleanup operations.
    :param int node_count: The number of nodes to request in the cluster.
    :returns: A ``Deferred`` which fires with a ``Cluster`` instance.
    """
    control_node = environ.get('FLOCKER_ACCEPTANCE_CONTROL_NODE')

    if control_node is None:
        raise SkipTest(
            "Set acceptance testing control node IP address using the " +
            "FLOCKER_ACCEPTANCE_CONTROL_NODE environment variable.")

    agent_nodes_env_var = environ.get('FLOCKER_ACCEPTANCE_AGENT_NODES')

    if agent_nodes_env_var is None:
        raise SkipTest(
            "Set acceptance testing node IP addresses using the " +
            "FLOCKER_ACCEPTANCE_AGENT_NODES environment variable and a " +
            "colon separated list.")

    agent_nodes = filter(None, agent_nodes_env_var.split(':'))

    if len(agent_nodes) < node_count:
        raise SkipTest("This test requires a minimum of {necessary} nodes, "
                       "{existing} node(s) are set.".format(
                           necessary=node_count, existing=len(agent_nodes)))

    return succeed(Cluster(
        control_node=Node(address=control_node),
        nodes=map(lambda address: Node(address=address), agent_nodes),
    ))


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
            u"name": random_name(),
            u"host": None,
            u"image": "clusterhq/flask:latest",
            u"ports": [{u"internal": 80, u"external": 8080}],
            u'restart_policy': {u'name': u'never'}
        }
        waiting_for_cluster = get_test_cluster(test_case=self, node_count=1)

        def create_container(cluster, data):
            data[u"host"] = cluster.nodes[0].address
            return cluster.create_container(data)

        d = waiting_for_cluster.addCallback(create_container, data)

        def check_result(result):
            cluster, response = result
            self.addCleanup(cluster.remove_container, data[u"name"])

            self.assertEqual(response, data)
            dl = verify_socket(data[u"host"], 8080)
            dl.addCallback(lambda _: (cluster, response))
            return dl

        d.addCallback(check_result)
        return d

    def test_create_container_with_ports(self):
        """
        Create a container including port mappings on a single-node cluster.
        """
        return self._create_container()

    def test_create_container_with_environment(self):
        """
        Create a container including environment variables on a single-node
        cluster.
        """
        data = {
            u"name": random_name(),
            u"host": None,
            u"image": "clusterhq/flaskenv:latest",
            u"ports": [{u"internal": 8080, u"external": 8081}],
            u"environment": {u"ACCEPTANCE_ENV_LABEL": 'acceptance test ok'},
            u'restart_policy': {u'name': u'never'},
        }
        waiting_for_cluster = get_test_cluster(test_case=self, node_count=1)

        def create_container(cluster, data):
            data[u"host"] = cluster.nodes[0].address
            return cluster.create_container(data)

        d = waiting_for_cluster.addCallback(create_container, data)

        def check_result((cluster, response)):
            self.addCleanup(cluster.remove_container, data[u"name"])
            self.assertEqual(response, data)

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
        d.addCallback(lambda _: verify_socket(data[u"host"], 8081))
        d.addCallback(lambda _: query_environment(data[u"host"], 8081))
        d.addCallback(
            lambda response:
                self.assertDictContainsSubset(data[u"environment"], response)
        )
        return d

    @require_mongo
    def test_move_container_with_dataset(self):
        """
        Create a mongodb container with an attached dataset, issue API call
        to move the container. Wait until we can connect to the running
        container on the new host and verify the data has moved with it.
        """
        creating_dataset = create_dataset(self, nodes=2)

        def created_dataset(result):
            cluster, dataset = result
            mongodb = {
                u"name": "container",
                u"host": cluster.nodes[0].address,
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
                    u"container", cluster.nodes[1].address
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
                    removed = cluster.remove_container(u"container")
                    mongodb2 = mongodb.copy()
                    mongodb2[u"ports"] = [
                        {u"internal": 27017, u"external": 27018}
                    ]
                    mongodb2[u"host"] = cluster.nodes[1].address
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
    def test_create_container_with_dataset(self):
        """
        Create a mongodb container with an attached dataset, insert some data,
        shut it down, create a new container with same dataset, make sure
        the data is still there.
        """
        creating_dataset = create_dataset(self)

        def created_dataset(result):
            cluster, dataset = result
            mongodb = {
                u"name": random_name(),
                u"host": cluster.nodes[0].address,
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

    def test_current(self):
        """
        The current container endpoint includes a currently running container.
        """
        creating = self._create_container()

        def created(result):
            cluster, data = result
            data[u"running"] = True

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
    waiting_for_cluster = get_test_cluster(
        test_case=test_case, node_count=nodes
    )

    # Configure a dataset on node1
    def configure_dataset(cluster):
        """
        Send a dataset creation request on node1.
        """
        requested_dataset = {
            u"primary": cluster.nodes[0].address,
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

    def test_dataset_move(self):
        """
        A dataset can be moved from one node to another.
        """
        # Create a 2 node cluster
        waiting_for_cluster = get_test_cluster(test_case=self, node_count=2)

        # Configure a dataset on node1
        def configure_dataset(cluster):
            """
            Send a dataset creation request on node1.
            """
            requested_dataset = {
                u"primary": cluster.nodes[0].address,
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
                u'primary': cluster.nodes[1].address
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

    def test_dataset_grow(self):
        """
        The size of a dataset can be increased.
        """
        creating = create_dataset(
            test_case=self, maximum_size=REALISTIC_BLOCKDEVICE_SIZE
        )
        new_size = REALISTIC_BLOCKDEVICE_SIZE * 2

        def resize_dataset(result):
            cluster, dataset = result
            return cluster.update_dataset(
                dataset["dataset_id"], {u'maximum_size': new_size}
            )

        resizing = creating.addCallback(resize_dataset)

        def check_dataset_size(result):
            cluster, dataset = result
            self.assertEqual(new_size, dataset['maximum_size'])
            return cluster.wait_for_dataset(dataset)

        checking = resizing.addCallback(check_dataset_size)

        return checking

    def test_dataset_shrink(self):
        """
        The size of a dataset can be decreased.
        """
        creating = create_dataset(
            test_case=self, maximum_size=REALISTIC_BLOCKDEVICE_SIZE * 2
        )
        new_size = REALISTIC_BLOCKDEVICE_SIZE

        def resize_dataset(result):
            cluster, dataset = result
            return cluster.update_dataset(
                dataset["dataset_id"], {u'maximum_size': new_size}
            )

        resizing = creating.addCallback(resize_dataset)

        def check_dataset_size(result):
            cluster, dataset = result
            self.assertEqual(new_size, dataset['maximum_size'])
            return cluster.wait_for_dataset(dataset)

        checking = resizing.addCallback(check_dataset_size)

        return checking

    def test_dataset_shrink_not_valid(self):
        """
        If the requested maximum_size is smaller than the allowed minimum the
        response is ``BAD_REQUEST``.
        """
        creating = create_dataset(
            test_case=self, maximum_size=REALISTIC_BLOCKDEVICE_SIZE
        )
        new_size = 67108864 - 1

        def resize_dataset(result):
            cluster, dataset = result
            # Reconfigure that dataset to be an invalid size.
            resizing = cluster.update_dataset(
                dataset_id=dataset["dataset_id"],
                dataset_properties={u'maximum_size': new_size}
            )
            # Check for expected exception and response code.
            return self.assertFailure(
                resizing, ValueError
            ).addCallback(
                lambda exception: self.assertEqual(
                    BAD_REQUEST, exception.args[1]
                )
            )

        return creating.addCallback(resize_dataset)

    def test_dataset_remove_size_limit(self):
        """
        A dataset with a size limit can have that limit removed.
        """
        creating = create_dataset(
            test_case=self, maximum_size=REALISTIC_BLOCKDEVICE_SIZE
        )
        new_size = None

        def resize_dataset(result):
            cluster, dataset = result
            return cluster.update_dataset(
                dataset["dataset_id"], {u'maximum_size': new_size}
            )

        resizing = creating.addCallback(resize_dataset)

        def check_dataset_size(result):
            cluster, dataset = result
            # If there is no maximum_size, the configuration response will not
            # contain that key
            self.assertNotIn(u'maximum_size', dataset.keys())
            return cluster.wait_for_dataset(dataset)

        checking = resizing.addCallback(check_dataset_size)

        return checking
