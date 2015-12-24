# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for ``flocker.node.testtools``.
"""

from testtools.deferredruntest import SynchronousDeferredRunTest
from twisted.internet.defer import succeed

from .. import sequentially
from ..testtools import (
    DummyDeployer, ControllableAction, ControllableDeployer,
    ideployer_tests_factory,
)
from ...control import NodeState
from .istatechange import make_istatechange_tests


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
    Tests for the ``IDeployer`` implementation of ``ControllableDeployer``.
    """

    # This test returns Deferreds but doesn't use the reactor.
    run_tests_with = SynchronousDeferredRunTest


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

    # This test returns Deferreds but doesn't use the reactor.
    run_tests_with = SynchronousDeferredRunTest
