# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for ``flocker.node._deploy``.
"""

from twisted.internet.defer import succeed

from twisted.trial.unittest import SynchronousTestCase

from zope.interface.verify import verifyObject

from ..testtools import (
    ControllableAction, ControllableDeployer, ideployer_tests_factory,
    EMPTY_NODE_STATE,
)
from ...control import (
    NodeState,
)

from .. import in_parallel

from .._deploy import (
    ILocalState, NodeLocalState,
)
from .istatechange import make_istatechange_tests


class NodeLocalStateTests(SynchronousTestCase):
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


class ControllableActionIStateChangeTests(
        make_istatechange_tests(
            ControllableAction,
            kwargs1=dict(result=1),
            kwargs2=dict(result=2),
        )
):
    """
    Tests for ``ControllableAction``.
    """


class ControllableDeployerInterfaceTests(
        ideployer_tests_factory(
            lambda test: ControllableDeployer(
                hostname=u"192.0.2.123",
                local_states=[succeed(NodeState(hostname=u'192.0.2.123'))],
                calculated_actions=[in_parallel(changes=[])],
            )
        )
):
    """
    ``IDeployer`` tests for ``ControllableDeployer``.
    """
