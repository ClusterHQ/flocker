# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for the control service REST API.
"""

import socket

from signal import SIGINT
from os import kill
from uuid import uuid4
from json import dumps, loads

from twisted.trial.unittest import TestCase
from treq import get, post, content
from characteristic import attributes

from .testtools import get_nodes, run_SSH
from ..testtools import loop_until

from ..control.httpapi import REST_API_PORT


def wait_for_api(hostname):
    """
    Wait until REST API is available.

    :param str hostname: The host where the control service is
         running.

    :return Deferred: Fires when REST API is available.
    """
    def api_available():
        try:
            s = socket.socket()
            s.connect((hostname, REST_API_PORT))
            return True
        except socket.error:
            return False
    return loop_until(api_available)


@attributes(['address', 'agents'])
class Node(object):
    """
    """


@attributes(['address', 'process'])
class RemoteService(object):
    """
    A record of a background SSH process and the node that it's running on.
    """


def close(process):
    process.stdin.close()
    kill(process.pid, SIGINT)


def remote_service_for_test(test_case, address, command):
    """
    Start a remote service for a test and register a cleanup function to stop
    it when the test finishes.
    """
    service = RemoteService(
        address=address,
        process=run_SSH(
            port=22,
            user='root',
            node=address,
            command=command,
            input=b"",
            key=None,
            background=True
        )
    )
    test_case.addCleanup(close, service.process)
    return service


@attributes(['control_service', 'nodes'])
class Cluster(object):
    """
    """
    @property
    def base_url(self):
        return b"http://{}:{}/v1".format(
            self.control_service.address, REST_API_PORT
        )

    def wait_for_dataset(self, dataset_properties):
        def created():
            request = get(self.base_url + b"/state/datasets", persistent=False)
            request.addCallback(content)

            def got_body(body):
                body = loads(body)
                # Current state listing includes bogus metadata
                # https://clusterhq.atlassian.net/browse/FLOC-1386
                expected_dataset = dataset_properties.copy()
                expected_dataset[u"metadata"].clear()
                return expected_dataset in body
            request.addCallback(got_body)
            return request

        waiting = loop_until(created)
        waiting.addCallback(lambda ignored: (self, dataset_properties))
        return waiting

    def create_dataset(self, dataset_properties):
        request = post(
            self.base_url + b"/configuration/datasets",
            data=dumps(dataset_properties),
            headers={b"content-type": b"application/json"},
            persistent=False
        )

        request.addCallback(content)
        request.addCallback(loads)
        # Return cluster and API response
        request.addCallback(lambda response: (self, response))
        return request

    def update_dataset(self, dataset_id, dataset_properties):
        request = post(
            self.base_url + b"/configuration/datasets/%s" % (
                dataset_id.encode('ascii'),
            ),
            data=dumps(dataset_properties),
            headers={b"content-type": b"application/json"},
            persistent=False
        )

        request.addCallback(content)
        request.addCallback(loads)
        # Return cluster and API response
        request.addCallback(lambda response: (self, response))
        return request


def cluster_for_test(test_case, node_addresses):
    # Start servers; eventually we will have these already running on
    # nodes, but for now needs to be done manually.
    # https://clusterhq.atlassian.net/browse/FLOC-1383

    # Control service is always started on node1
    control_service = remote_service_for_test(
        test_case, sorted(node_addresses)[0], [b"flocker-control"]
    )

    # https://clusterhq.atlassian.net/browse/FLOC-1382
    nodes = []
    for node_address in node_addresses:
        agent_service = remote_service_for_test(
            test_case,
            node_address,
            [b"flocker-zfs-agent", node_address, control_service.address],
        )
        node = Node(
            address=node_address,
            agents=[agent_service]
        )
        nodes.append(node)

    return Cluster(control_service=control_service, nodes=nodes)


def create_cluster_and_wait_for_api(test_case, nodes):
    """
    """
    cluster = cluster_for_test(test_case, nodes)
    waiting = wait_for_api(cluster.control_service.address)
    api_ready = waiting.addCallback(lambda ignored: cluster)
    return api_ready


def wait_for_cluster(test_case, node_count):
    """
    """
    getting_nodes = get_nodes(test_case, node_count)

    getting_nodes.addCallback(
        lambda nodes: create_cluster_and_wait_for_api(test_case, nodes)
    )

    return getting_nodes


class DatasetAPITests(TestCase):
    """
    Tests for the dataset API.
    """
    def test_dataset_creation(self):
        """
        A dataset can be created on a specific node.
        """
        d = get_nodes(self, 1)
        d.addCallback(self._test_dataset_creation)
        return d

    def _test_dataset_creation(self, nodes):
        """
        Run the actual test now that the nodes are available.

        :param nodes: Sequence of available hostnames, of size 1.
        """
        node_1, = nodes

        def close(process):
            process.stdin.close()
            kill(process.pid, SIGINT)
        # Start servers; eventually we will have these already running on
        # nodes, but for now needs to be done manually.
        # https://clusterhq.atlassian.net/browse/FLOC-1383
        p1 = run_SSH(22, 'root', node_1, [b"flocker-control"],
                     b"", None, True)
        self.addCleanup(close, p1)

        # https://clusterhq.atlassian.net/browse/FLOC-1382
        p2 = run_SSH(22, 'root', node_1,
                     [b"flocker-zfs-agent", node_1, b"localhost"],
                     b"", None, True)
        self.addCleanup(close, p2)

        d = wait_for_api(node_1)

        uuid = unicode(uuid4())
        dataset = {u"primary": node_1,
                   u"dataset_id": uuid,
                   u"metadata": {u"name": u"my_volume"}}
        base_url = b"http://{}:{}/v1".format(node_1, REST_API_PORT)
        d.addCallback(
            lambda _: post(base_url + b"/configuration/datasets",
                           data=dumps(dataset),
                           headers={b"content-type": b"application/json"},
                           persistent=False))
        d.addCallback(content)

        def got_result(result):
            result = loads(result)
            self.assertEqual(dataset, result)
        d.addCallback(got_result)

        def created():
            result = get(base_url + b"/state/datasets", persistent=False)
            result.addCallback(content)

            def got_body(body):
                body = loads(body)
                # Current state listing includes bogus metadata
                # https://clusterhq.atlassian.net/browse/FLOC-1386
                expected_dataset = dataset.copy()
                expected_dataset[u"metadata"].clear()
                return expected_dataset in body
            result.addCallback(got_body)
            return result
        d.addCallback(lambda _: loop_until(created))
        return d

    def test_dataset_move(self):
        """
        A dataset can be moved from one node to another.
        """
        # Create a 2 node cluster
        waiting_for_cluster = wait_for_cluster(test_case=self, node_count=2)

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
