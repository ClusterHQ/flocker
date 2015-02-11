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

from .testtools import get_nodes, _run_SSH
from ..testtools import loop_until

from ..control.httpapi import REST_API_PORT


def wait_for_api(hostname):
    """
    Wait until REST API is available.

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


class DatasetAPITests(TestCase):
    """
    Tests for the dataset API.
    """
    def test_dataset_creation(self):
        """
        A dataset can be created on a specific node.
        """
        # This is blocking for now, may as well due this the succinct way:
        node_1, = self.successResultOf(get_nodes(self, 1))
        # Start servers; eventually we will have these already running on
        # nodes, but for now needs to be done manually.
        # https://clusterhq.atlassian.net/browse/FLOC-1383
        p1 = _run_SSH(22, 'root', node_1, [b"flocker-control"],
                      b"", None, True)
        # https://clusterhq.atlassian.net/browse/FLOC-1382
        p2 = _run_SSH(22, 'root', node_1,
                      [b"flocker-zfs-agent", node_1, b"localhost"],
                      b"", None, True)

        def close(process):
            process.stdin.close()
            kill(process.pid, SIGINT)
        self.addCleanup(close, p1)
        self.addCleanup(close, p2)

        d = wait_for_api(node_1)

        uuid = unicode(uuid4())
        dataset = {u"primary": node_1,
                   u"dataset_id": uuid,
                   u"metadata": {u"name": u"my_volume"}}
        base_url = "http://{}:{}/v1".format(node_1, REST_API_PORT)
        d.addCallback(
            lambda _: post(base_url + "/datasets",
                           data=dumps(dataset),
                           headers={"content-type": "application/json"},
                           persistent=False))
        d.addCallback(content)

        def got_result(result):
            result = loads(result)
            self.assertEqual(dataset, result)
        d.addCallback(got_result)

        def created():
            result = get(base_url + "/state/datasets", persistent=False)
            result.addCallback(content)

            def got_body(body):
                body = loads(body)
                # Current state listing doesn't include metadata.
                expected_dataset = dataset.copy()
                expected_dataset["metadata"].clear()
                return expected_dataset in body
            result.addCallback(got_body)
            return result
        d.addCallback(lambda _: loop_until(created))
        return d
