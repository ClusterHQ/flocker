# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for ``flocker.node.testtools``.
"""

from zope.interface import implementer

from twisted.internet.defer import succeed

from .. import sequentially
from ..testtools import (
    DummyDeployer, ControllableDeployer, ideployer_tests_factory,
)
from ...control import IClusterStateChange


@implementer(IClusterStateChange)
class DummyClusterStateChange(object):
    """
    A non-implementation of ``IClusterStateChange``.
    """
    def update_cluster_state(self, cluster_state):
        return cluster_state


class DummyDeployerIDeployerTests(
    ideployer_tests_factory(lambda case: DummyDeployer())
):
    """
    Tests for the ``IDeployer`` implementation of ``DummyDeployer``.
    """


class ControllableDeployerIDeployerTests(
    ideployer_tests_factory(
        lambda case: ControllableDeployer(
            hostname=u"10.0.0.1",
            local_states=[succeed(DummyClusterStateChange())],
            calculated_actions=[sequentially(changes=[])],
        )
    )
):
    """
    Tests for the ``IDeployer`` implementation of ``DummyDeployer``.
    """
