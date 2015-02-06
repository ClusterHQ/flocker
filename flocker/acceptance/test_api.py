# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for the control service REST API.
"""

import time
from uuid import uuid4
from json import dumps

from twisted.trial.unittest import TestCase

from treq import GET, POST, json_content

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
        # Start servers:
        _run_SSH(22, 'root', b"nohup flocker-control &", b"")
        _run_SSH(22, 'root', b"nohup flocker-zfs-agent localhost &", b"")

        # XXX loop until REST service is up.
        time.sleep(3)

        uuid = unicode(uuid4())
        dataset = {u"primary": node_1,
                   u"dataset_id": uuid,
                   u"metadata": {u"name": u"myvolume"}}
        d = POST("http://{}:4523/datasets".format(node_1), data=dumps(dataset))
        d.addCallback(json_content)
        d.addCallback(self.assertEqual, dataset)

        def created(_):
            # XXX loop until this succeeds
            time.sleep(5)
            return GET("http://{}:4523/state/datasets".format(node_1))
        d.addCallback(created)
        d.addCallback(json_content)
        d.addCallback(lambda results: self.assertIn(dataset, results))
        return d
