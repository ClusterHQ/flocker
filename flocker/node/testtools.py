# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Testing utilities for ``flocker.node``.
"""

from uuid import uuid4

from zope.interface import implementer

from characteristic import attributes

from twisted.internet.defer import succeed

from zope.interface.verify import verifyObject

from eliot import Logger, ActionType

from . import (
    ILocalState, IDeployer, NodeLocalState, IStateChange, sequentially
)
from ..common import loop_until
from ..testtools import AsyncTestCase
from ..control import (
    IClusterStateChange, Node, NodeState, Deployment, DeploymentState,
    PersistentState,
)
from ..control._model import ip_to_uuid, Leases


def wait_for_unit_state(reactor, docker_client, unit_name,
                        expected_activation_states):
    """
    Wait until a unit is in the requested state.

    :param IReactorTime reactor: The reactor implementation to use to delay.
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

    return loop_until(reactor, check_if_in_states)


CONTROLLABLE_ACTION_TYPE = ActionType(u"test:controllableaction", [], [])


@implementer(IStateChange)
@attributes(['result'])
class ControllableAction(object):
    """
    ``IStateChange`` whose results can be controlled.
    """
    called = False
    deployer = None
    state_persister = None

    _logger = Logger()

    @property
    def eliot_action(self):
        return CONTROLLABLE_ACTION_TYPE(self._logger)

    def run(self, deployer, state_persister):
        self.called = True
        self.deployer = deployer
        self.state_persister = state_persister
        return self.result


@implementer(ILocalState)
class DummyLocalState(object):
    """
    A non-implementation of ``ILocalState``.
    """

    def shared_state_changes(self):
        """
        A non-implementation that returns an empty tuple.
        """
        return ()


@implementer(IDeployer)
class DummyDeployer(object):
    """
    A non-implementation of ``IDeployer``.
    """
    hostname = u"127.0.0.1"
    node_uuid = uuid4()

    def discover_state(self, cluster_state, persistent_state):
        return succeed(DummyLocalState())

    def calculate_changes(self, desired_configuration, cluster_state,
                          local_state):
        return sequentially(changes=[])


@implementer(IDeployer)
class ControllableDeployer(object):
    """
    ``IDeployer`` whose results can be controlled for any ``NodeLocalState``.
    """
    def __init__(self, hostname, local_states, calculated_actions):
        """
        :param list local_states: A list of results to produce from
            ``discover_state``.  Each call to ``discover_state`` pops the first
            element from this list and uses it as its result.  If the element
            is an exception, it is raised.  Otherwise it must be a
            ``Deferred`` that resolves to a ``NodeState``. This ``IDeployer``
            always returns a ``NodeLocalState`` from ``discover_state``.
        """
        self.node_uuid = ip_to_uuid(hostname)
        self.hostname = hostname
        self.local_states = local_states
        self.calculated_actions = calculated_actions
        self.calculate_inputs = []
        self.discover_inputs = []

    def discover_state(self, cluster_state, persistent_state):
        self.discover_inputs.append((cluster_state, persistent_state))
        state = self.local_states.pop(0)
        if isinstance(state, Exception):
            raise state
        else:
            return state.addCallback(
                lambda val: NodeLocalState(node_state=val))

    def calculate_changes(self, desired_configuration, cluster_state,
                          local_state):
        self.calculate_inputs.append(
            (cluster_state.get_node(uuid=self.node_uuid,
                                    hostname=self.hostname),
             desired_configuration, cluster_state))
        calculated = self.calculated_actions.pop(0)
        if isinstance(calculated, Exception):
            raise calculated
        else:
            return calculated


# A deployment with no information:
EMPTY = Deployment(nodes=[])
EMPTY_STATE = DeploymentState()
EMPTY_NODE_STATE = NodeState(uuid=uuid4(), hostname=u"example.com")


def empty_node_local_state(ideployer):
    """
    Constructs an ``NodeLocalState`` from an ideployer. Only uuid and
    hostname of the ``node_state`` will be filled in, everything else will be
    left as None to signify that we are ignorant of the proper value.

    :param IDeployer ideployer: The ``IDeployer`` provider to get the hostname
        and uuid from.
    """
    return NodeLocalState(node_state=NodeState(uuid=ideployer.node_uuid,
                          hostname=ideployer.hostname))


def ideployer_tests_factory(fixture):
    """
    Create test case for IDeployer implementation.

    :param fixture: Callable that takes ``TestCase`` instance and returns
         a ``IDeployer`` provider.

    :return: ``TestCase`` subclass that will test the given fixture.
    """
    class IDeployerTests(AsyncTestCase):
        """
        Tests for ``IDeployer``.
        """

        def _make_deployer(self):
            """
            Make the ``IDeployer`` under test.
            """
            return fixture(self)

        def test_interface(self):
            """
            The object claims to provide the interface.
            """
            self.assertTrue(verifyObject(IDeployer, self._make_deployer()))

        def _discover_state(self):
            """
            Create a deployer using the fixture and ask it to discover state.

            :return: The return value of the object's ``discover_state``
                method.
            """
            # XXX: Why is this set on the instance? Is it re-used? Does it
            # cache?
            self._deployer = self._make_deployer()
            result = self._deployer.discover_state(
                DeploymentState(nodes={NodeState(hostname=b"10.0.0.1")}),
                persistent_state=PersistentState(),
            )
            return result

        def test_discover_state_ilocalstate_result(self):
            """
            The object's ``discover_state`` method returns a ``Deferred`` that
            fires with a ``ILocalState`` provider.
            """
            def discovered(local_state):
                self.assertTrue(ILocalState.providedBy(local_state))
                self.assertEqual(tuple,
                                 type(local_state.shared_state_changes()))
            return self._discover_state().addCallback(discovered)

        def test_discover_state_iclusterstatechange(self):
            """
            The elements of the ``tuple`` that ``shared_state_changes`` returns
            will provide ``IClusterStateChange``.
            """
            def discovered(local_state):
                changes = local_state.shared_state_changes()
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
            # ``local_state`` (an argument to ``calculate_changes``) has an
            # opaque type, specific to this implementation of ``IDeployer``.
            # Rather than generating an arbitrary ``local_state`` generate one
            # by calling ``discover_state``.
            def discovered(local_state):
                result = self._deployer.calculate_changes(
                    EMPTY, EMPTY_STATE, local_state)
                self.assertTrue(verifyObject(IStateChange, result))
            return self._discover_state().addCallback(discovered)

    return IDeployerTests


def to_node(node_state):
    """
    Convert a ``NodeState`` to a corresponding ``Node``.

    :param NodeState node_state: Object to convert.
    :return Node: Equivalent node.
    """
    return Node(uuid=node_state.uuid, hostname=node_state.hostname,
                applications=node_state.applications or {},
                manifestations=node_state.manifestations or {})


def compute_cluster_state(node_state, additional_node_states,
                          nonmanifest_datasets):
    """
    Computes the cluster_state from the passed in arguments.

    :param NodeState node_state: The deployer will be asked to calculate
        changes for a node that has this state.

    :param set additional_node_states: A set of ``NodeState`` for other nodes.

    :param set nonmanifest_datasets: Datasets which will be presented as part
        of the cluster state without manifestations on any node.

    :returns: A DeploymentState encoding all of the parameters.
    """
    return DeploymentState(
        nodes={node_state} | additional_node_states,
        nonmanifest_datasets={
            dataset.dataset_id: dataset
            for dataset in nonmanifest_datasets
        },
    )


def assert_calculated_changes_for_deployer(
    case, deployer, node_state, node_config, nonmanifest_datasets,
    additional_node_states, additional_node_config, expected_changes,
    local_state, leases=Leases()
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
    :param ILocalState local_state: The ``local_state`` to pass into
        ``calculate_changes``. Must be the correct type for the type of
        ``IDeployer`` being tested.
    :param Leases leases: Currently configured leases. By default none exist.
    """
    cluster_state = compute_cluster_state(node_state, additional_node_states,
                                          nonmanifest_datasets)
    cluster_configuration = Deployment(
        nodes={node_config} | additional_node_config,
        leases=leases,
    )
    changes = deployer.calculate_changes(
        cluster_configuration, cluster_state, local_state
    )
    case.assertEqual(expected_changes, changes)
