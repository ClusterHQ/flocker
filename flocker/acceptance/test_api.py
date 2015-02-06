# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for the control service REST API.
"""

import time
from uuid import uuid4
from json import dumps, loads

from twisted.trial.unittest import TestCase

from treq import get, post, content

from .testtools import get_nodes, _run_SSH


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
        # Start servers:1
        _run_SSH(22, 'root', node_1, [b"flocker-control"], b"", None, True)
        _run_SSH(22, 'root', node_1, [b"flocker-zfs-agent", b"localhost"],
                 b"", None, True)

        # XXX loop until REST service is up.
        time.sleep(3)

        uuid = unicode(uuid4())
        dataset = {u"primary": node_1,
                   u"dataset_id": uuid,
                   u"metadata": {u"name": u"myvolume"}}
        d = post("http://{}:4523/v1/datasets".format(node_1),
                 data=dumps(dataset),
                 headers={"content-type": "application/json"})
        d.addCallback(content)

        def got_result(result):
            result = loads(result)
            self.assertEqual(dataset, result)
        d.addCallback(got_result)

        def created(_):
            # XXX loop until this succeeds
            time.sleep(5)
            return get("http://{}:4523/v1/state/datasets".format(node_1))
        d.addCallback(created)
        d.addCallback(content)

        def got_result2(result):
            print result
            result = loads(result)
            self.assertIn(dataset, result)

        d.addCallback(got_result2)
        return d
