# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for ``flocker.node._deploy``.
"""

from zope.interface.verify import verifyObject

from ..testtools import EMPTY_NODE_STATE
from ...testtools import TestCase

from .._deploy import ILocalState, NodeLocalState


class NodeLocalStateTests(TestCase):
    """
    Tests for ``NodeLocalState``
    """

    def test_ilocalstate(self):
        """
        ``NodeLocalState`` instances provide ``ILocalState``
        """
        self.assertTrue(
            verifyObject(ILocalState,
                         NodeLocalState(node_state=EMPTY_NODE_STATE))
        )

    def test_node_state_reported(self):
        """
        ``NodeLocalState`` should return the node_state in a tuple when
        shared_state_changes() is called.
        """
        node_state = EMPTY_NODE_STATE
        object_under_test = NodeLocalState(node_state=node_state)
        self.assertEqual((node_state,),
                         object_under_test.shared_state_changes())
