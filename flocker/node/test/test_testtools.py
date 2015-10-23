# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for ``flocker.node.testtools``.
"""

from twisted.internet.defer import succeed

from .. import sequentially
from ..testtools import (
    DummyDeployer, ControllableDeployer, ideployer_tests_factory,
)
from ...control import NodeState


class DummyDeployerIDeployerTests(
    ideployer_tests_factory(lambda case: DummyDeployer())
):
    """
    Tests for the ``IDeployer`` implementation of ``DummyDeployer``.
    """


_HOSTNAME = u"10.0.0.1"


class ControllableDeployerIDeployerTests(
    ideployer_tests_factory(
        lambda case: ControllableDeployer(
            hostname=_HOSTNAME,
            local_states=[succeed(NodeState(hostname=_HOSTNAME))],
            calculated_actions=[sequentially(changes=[])],
        )
    )
):
    """
    Tests for the ``IDeployer`` implementation of ``DummyDeployer``.
    """
