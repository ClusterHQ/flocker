# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Testing utilities for ``flocker.node``.
"""

import os
import pwd
import socket
from unittest import skipIf
from contextlib import closing
from uuid import uuid4

from zope.interface import implementer

from characteristic import attributes

from twisted.trial.unittest import TestCase
from twisted.internet.defer import succeed

from zope.interface.verify import verifyObject

from eliot import Logger, ActionType

from ._docker import BASE_DOCKER_API_URL
from . import IDeployer, IStateChange, sequentially
from ..testtools import loop_until
from ..control import (
    IClusterStateChange, Node, NodeState, Deployment, DeploymentState)
from ..control._model import ip_to_uuid

DOCKER_SOCKET_PATH = BASE_DOCKER_API_URL.split(':/')[-1]


def docker_accessible():
    """
    Attempt to connect to the Docker control socket.

    This may address https://clusterhq.atlassian.net/browse/FLOC-85.

    :return: A ``bytes`` string describing the reason Docker is not
        accessible or ``None`` if it appears to be accessible.
    """
    try:
        with closing(socket.socket(family=socket.AF_UNIX)) as docker_socket:
            docker_socket.connect(DOCKER_SOCKET_PATH)
    except socket.error as e:
        return os.strerror(e.errno)
    return None

_docker_reason = docker_accessible()

if_docker_configured = skipIf(
    _docker_reason,
    "User {!r} cannot access Docker via {!r}: {}".format(
        pwd.getpwuid(os.geteuid()).pw_name,
        DOCKER_SOCKET_PATH,
        _docker_reason,
    ))


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


CONTROLLABLE_ACTION_TYPE = ActionType(u"test:controllableaction", [], [])


@implementer(IStateChange)
@attributes(['result'])
class ControllableAction(object):
    """
    ``IStateChange`` whose results can be controlled.
    """
    called = False
    deployer = None

    _logger = Logger()

    @property
    def eliot_action(self):
        return CONTROLLABLE_ACTION_TYPE(self._logger)

    def run(self, deployer):
        self.called = True
        self.deployer = deployer
        return self.result


@implementer(IDeployer)
class DummyDeployer(object):
    """
    A non-implementation of ``IDeployer``.
    """
    hostname = u"127.0.0.1"
    node_uuid = uuid4()

    def discover_state(self, node_stat):
        return succeed(())

    def calculate_changes(self, desired_configuration, cluster_state):
        return sequentially(changes=[])


@implementer(IDeployer)
class ControllableDeployer(object):
    """
    ``IDeployer`` whose results can be controlled.
    """
    def __init__(self, hostname, local_states, calculated_actions):
        self.node_uuid = ip_to_uuid(hostname)
        self.hostname = hostname
        self.local_states = local_states
        self.calculated_actions = calculated_actions
        self.calculate_inputs = []

    def discover_state(self, node_state):
        return self.local_states.pop(0).addCallback(lambda val: (val,))

    def calculate_changes(self, desired_configuration, cluster_state):
        self.calculate_inputs.append(
            (cluster_state.get_node(uuid=self.node_uuid,
                                    hostname=self.hostname),
             desired_configuration, cluster_state))
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
            result = deployer.calculate_changes(EMPTY, EMPTY_STATE)
            self.assertTrue(verifyObject(IStateChange, result))

    return IDeployerTests


def to_node(node_state):
    """
    Convert a ``NodeState`` to a corresponding ``Node``.

    :param NodeState node_state: Object to convert.
    :return Node: Equivalent node.
    """
    return Node(uuid=node_state.uuid, hostname=node_state.hostname,
                applications=node_state.applications or [],
                manifestations=node_state.manifestations or {})


def assert_calculated_changes_for_deployer(
        case, deployer, node_state, node_config, nonmanifest_datasets,
        additional_node_states, additional_node_config, expected_changes
):
    """
    Assert that ``calculate_changes`` returns certain changes when it is
    invoked with the given state and configuration.

    :param TestCase case: The ``TestCase`` to use to make assertions (typically
        the one being run at the moment).
    :param IDeployer deployer: The deployer provider which will be asked to
        calculate the changes.
    :param NodeState node_state: The deployer will be asked to calculate
        changes for a node that has this state.
    :param Node node_config: The deployer will be asked to calculate changes
        for a node with this desired configuration.
    :param set nonmanifest_datasets: Datasets which will be presented as part
        of the cluster state without manifestations on any node.
    :param set additional_node_states: A set of ``NodeState`` for other nodes.
    :param set additional_node_config: A set of ``Node`` for other nodes.
    :param expected_changes: The ``IStateChange`` expected to be returned.
    """
    cluster_state = DeploymentState(
        nodes={node_state} | additional_node_states,
        nonmanifest_datasets={
            dataset.dataset_id: dataset
            for dataset in nonmanifest_datasets
        },
    )
    cluster_configuration = Deployment(
        nodes={node_config} | additional_node_config,
    )
    changes = deployer.calculate_changes(
        cluster_configuration, cluster_state,
    )
    case.assertEqual(expected_changes, changes)
