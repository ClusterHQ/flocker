# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Testing utilities for ``flocker.node``.
"""

import errno
import os
import pwd
import socket
from unittest import skipUnless

from zope.interface import implementer

from characteristic import attributes

from twisted.trial.unittest import TestCase

from zope.interface.verify import verifyObject

from ._deploy import _OldToNewDeployer
from ._docker import BASE_DOCKER_API_URL
from . import IDeployer, IStateChange
from ..testtools import loop_until
from ..control import (
    IClusterStateChange, Node, NodeState, Deployment, DeploymentState)

DOCKER_SOCKET_PATH = BASE_DOCKER_API_URL.split(':/')[-1]


def docker_accessible():
    """
    Attempt to connect to the Docker control socket.

    This may address https://clusterhq.atlassian.net/browse/FLOC-85.

    :return: ``True`` if the current user has permission to connect, else
        ``False``.
    """
    try:
        socket.socket(family=socket.AF_UNIX).connect(DOCKER_SOCKET_PATH)
    except socket.error as e:
        if e.errno == errno.EACCES:
            return False
        if e.errno == errno.ENOENT:
            # Docker is not installed
            return False
        raise
    else:
        return True

if_docker_configured = skipUnless(
    docker_accessible(),
    "User '{}' does not have permission "
    "to access the Docker server socket '{}'".format(
        pwd.getpwuid(os.geteuid()).pw_name,
        DOCKER_SOCKET_PATH))


def wait_for_unit_state(docker_client, unit_name, expected_activation_states):
    """
    Wait until a unit is in the requested state.

    :param docker_client: A ``DockerClient`` instance.
    :param unicode unit_name: The name of the unit.
    :param expected_activation_states: Activation states to wait for.

    :return: ``Deferred`` that fires when required state has been reached.
    """
    def is_in_states(units):
        for unit in units:
            if unit.name == unit_name:
                if unit.activation_state in expected_activation_states:
                    return True

    def check_if_in_states():
        responded = docker_client.list()
        responded.addCallback(is_in_states)
        return responded

    return loop_until(check_if_in_states)


@implementer(IStateChange)
@attributes(['result'])
class ControllableAction(object):
    """
    ``IStateChange`` whose results can be controlled.
    """
    called = False
    deployer = None

    def run(self, deployer):
        self.called = True
        self.deployer = deployer
        return self.result


@implementer(IDeployer)
class ControllableDeployer(_OldToNewDeployer):
    """
    ``IDeployer`` whose results can be controlled.
    """
    def __init__(self, hostname, local_states, calculated_actions):
        self.hostname = hostname
        self.local_states = local_states
        self.calculated_actions = calculated_actions
        self.calculate_inputs = []

    def discover_local_state(self, node_state):
        return self.local_states.pop(0)

    def calculate_necessary_state_changes(self, local_state,
                                          desired_configuration,
                                          cluster_state):
        self.calculate_inputs.append(
            (local_state, desired_configuration, cluster_state))
        return self.calculated_actions.pop(0)


# A deployment with no information:
EMPTY = Deployment(nodes=[])
EMPTY_STATE = DeploymentState()


def ideployer_tests_factory(fixture):
    """
    Create test case for IDeployer implementation.

    :param fixture: Callable that takes ``TestCase`` instance and returns
         a ``IDeployer`` provider.

    :return: ``TestCase`` subclass that will test the given fixture.
    """
    class IDeployerTests(TestCase):
        """
        Tests for ``IDeployer``.
        """
        def test_interface(self):
            """
            The object claims to provide the interface.
            """
            self.assertTrue(verifyObject(IDeployer, fixture(self)))

        def _discover_state(self):
            """
            Create a deployer using the fixture and ask it to discover state.

            :return: The return value of the object's ``discover_state``
                method.
            """
            deployer = fixture(self)
            result = deployer.discover_state(NodeState(hostname=b"10.0.0.1"))
            return result

        def test_discover_state_list_result(self):
            """
            The object's ``discover_state`` method returns a ``Deferred`` that
            fires with a ``list``.
            """
            def discovered(changes):
                self.assertEqual(tuple, type(changes))
            return self._discover_state().addCallback(discovered)

        def test_discover_state_iclusterstatechange(self):
            """
            The elements of the ``list`` that ``discover_state``\ 's
            ``Deferred`` fires with provide ``IClusterStateChange``.
            """
            def discovered(changes):
                wrong = []
                for obj in changes:
                    if not IClusterStateChange.providedBy(obj):
                        wrong.append(obj)
                if wrong:
                    template = (
                        "Some elements did not provide IClusterStateChange: {}"
                    )
                    self.fail(template.format(wrong))
            return self._discover_state().addCallback(discovered)

        def test_calculate_necessary_state_changes(self):
            """
            The object's ``calculate_necessary_state_changes`` method returns a
            ``IStateChange`` provider.
            """
            deployer = fixture(self)
            result = deployer.calculate_changes(EMPTY, EMPTY)
            self.assertTrue(verifyObject(IStateChange, result))

    return IDeployerTests


def to_node(node_state):
    """
    Convert a ``NodeState`` to a corresponding ``Node``.

    :param NodeState node_state: Object to convert.
    :return Node: Equivalent node.
    """
    return Node(hostname=node_state.hostname,
                applications=node_state.applications,
                manifestations=node_state.manifestations)
