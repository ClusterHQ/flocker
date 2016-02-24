# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for ``flocker.node._loop``.
"""

from itertools import repeat
import math
from uuid import uuid4
from datetime import timedelta

from eliot.testing import (
    validate_logging, assertHasAction, assertHasMessage, capture_logging,
)
from machinist import LOG_FSM_TRANSITION
from hypothesis import assume, given
from hypothesis.strategies import floats

from pyrsistent import pset

from twisted.test.proto_helpers import MemoryReactorClock
from twisted.internet.protocol import ReconnectingClientFactory
from twisted.internet.defer import succeed, Deferred, fail
from twisted.internet.ssl import ClientContextFactory
from twisted.internet.task import Clock
from twisted.protocols.tls import TLSMemoryBIOFactory, TLSMemoryBIOProtocol
from twisted.protocols.amp import AMP, CommandLocator
from twisted.test.iosim import connectedServerAndClient

from ...testtools.amp import (
    FakeAMPClient, DelayedAMPClient, connected_amp_protocol,
)
from ...testtools import CustomException, TestCase
from .._loop import (
    build_cluster_status_fsm, ClusterStatusInputs, _ClientStatusUpdate,
    _StatusUpdate, _ConnectedToControlService, ConvergenceLoopInputs,
    ConvergenceLoopStates, build_convergence_loop_fsm, AgentLoopService,
    LOG_SEND_TO_CONTROL_SERVICE,
    LOG_CONVERGE, LOG_CALCULATED_ACTIONS, LOG_DISCOVERY,
    _UNCONVERGED_DELAY, _UNCONVERGED_BACKOFF_FACTOR, _Sleep,
    RemoteStatePersister, _UnconvergedDelay,
    )
from ..testtools import (
    ControllableDeployer, ControllableAction, to_node, NodeLocalState,
)
from ...control import (
    NodeState, Deployment, Manifestation, Dataset, DeploymentState,
    Application, DockerImage, PersistentState,
)
from ...control._protocol import NodeStateCommand, AgentAMP, SetNodeEraCommand
from ...control.testtools import (
    make_istatepersister_tests,
    make_loopback_control_client,
)
from ...control.test.test_protocol import (
    iconvergence_agent_tests_factory,
)
from .. import NoOp


NO_OP = NoOp(sleep=timedelta(seconds=300))


class StubFSM(object):
    """
    A finite state machine look-alike that just records inputs.
    """
    def __init__(self):
        self.inputted = []

    def receive(self, symbol):
        self.inputted.append(symbol)


class ClusterStatusFSMTests(TestCase):
    """
    Tests for the cluster status FSM.
    """
    def setUp(self):
        super(ClusterStatusFSMTests, self).setUp()
        self.convergence_loop = StubFSM()
        self.fsm = build_cluster_status_fsm(self.convergence_loop)

    def assertConvergenceLoopInputted(self, expected):
        """
        Assert that that given set of symbols were input to the agent
        operation FSM.
        """
        self.assertEqual(self.convergence_loop.inputted, expected)

    def test_creation_no_side_effects(self):
        """
        Creating the FSM has no side effects.
        """
        self.assertConvergenceLoopInputted([])

    def test_first_status_update(self):
        """
        Once the client has been connected and a status update received it
        notifies the convergence loop FSM of this.
        """
        client = object()
        desired = object()
        state = object()
        self.fsm.receive(_ConnectedToControlService(client=client))
        self.fsm.receive(_StatusUpdate(configuration=desired, state=state))
        self.assertConvergenceLoopInputted(
            [_ClientStatusUpdate(client=client, configuration=desired,
                                 state=state)])

    def test_second_status_update(self):
        """
        Further status updates are also passed to the convergence loop FSM.
        """
        client = object()
        desired1 = object()
        state1 = object()
        desired2 = object()
        state2 = object()
        self.fsm.receive(_ConnectedToControlService(client=client))
        # Initially some other status:
        self.fsm.receive(_StatusUpdate(configuration=desired1, state=state1))
        self.fsm.receive(_StatusUpdate(configuration=desired2, state=state2))
        self.assertConvergenceLoopInputted(
            [_ClientStatusUpdate(client=client, configuration=desired1,
                                 state=state1),
             _ClientStatusUpdate(client=client, configuration=desired2,
                                 state=state2)])

    def test_status_update_no_disconnect(self):
        """
        Neither new connections nor status updates cause the client to be
        disconnected.
        """
        client = connected_amp_protocol()
        self.fsm.receive(_ConnectedToControlService(client=client))
        self.fsm.receive(_StatusUpdate(configuration=object(),
                                       state=object()))
        self.assertFalse(client.transport.disconnecting)

    def test_disconnect_before_status_update(self):
        """
        If the client disconnects before a status update is received then no
        notification is needed for convergence loop FSM.
        """
        self.fsm.receive(
            _ConnectedToControlService(client=connected_amp_protocol()))
        self.fsm.receive(ClusterStatusInputs.DISCONNECTED_FROM_CONTROL_SERVICE)
        self.assertConvergenceLoopInputted([])

    def test_disconnect_after_status_update(self):
        """
        If the client disconnects after a status update is received then the
        convergence loop FSM is notified.
        """
        client = object()
        desired = object()
        state = object()
        self.fsm.receive(_ConnectedToControlService(client=client))
        self.fsm.receive(_StatusUpdate(configuration=desired, state=state))
        self.fsm.receive(ClusterStatusInputs.DISCONNECTED_FROM_CONTROL_SERVICE)
        self.assertConvergenceLoopInputted(
            [_ClientStatusUpdate(client=client, configuration=desired,
                                 state=state),
             ConvergenceLoopInputs.STOP])

    def test_status_update_after_reconnect(self):
        """
        If the client disconnects, reconnects, and a new status update is
        received then the convergence loop FSM is notified.
        """
        client = object()
        desired = object()
        state = object()
        self.fsm.receive(_ConnectedToControlService(client=client))
        self.fsm.receive(_StatusUpdate(configuration=desired, state=state))
        self.fsm.receive(ClusterStatusInputs.DISCONNECTED_FROM_CONTROL_SERVICE)
        client2 = object()
        desired2 = object()
        state2 = object()
        self.fsm.receive(_ConnectedToControlService(client=client2))
        self.fsm.receive(_StatusUpdate(configuration=desired2, state=state2))
        self.assertConvergenceLoopInputted(
            [_ClientStatusUpdate(client=client, configuration=desired,
                                 state=state),
             ConvergenceLoopInputs.STOP,
             _ClientStatusUpdate(client=client2, configuration=desired2,
                                 state=state2)])

    def test_shutdown_before_connect(self):
        """
        If the FSM is shutdown before a connection is made nothing happens.
        """
        self.fsm.receive(ClusterStatusInputs.SHUTDOWN)
        self.assertConvergenceLoopInputted([])

    def test_shutdown_after_connect(self):
        """
        If the FSM is shutdown after connection but before status update is
        received then it disconnects but does not notify the agent
        operation FSM.
        """
        client = connected_amp_protocol()
        self.fsm.receive(_ConnectedToControlService(client=client))
        self.fsm.receive(ClusterStatusInputs.SHUTDOWN)
        self.assertEqual((client.transport.disconnecting,
                          self.convergence_loop.inputted),
                         (True, []))

    def test_shutdown_after_status_update(self):
        """
        If the FSM is shutdown after connection and status update is received
        then it disconnects and also notifys the convergence loop FSM that
        is should stop.
        """
        client = connected_amp_protocol()
        desired = object()
        state = object()
        self.fsm.receive(_ConnectedToControlService(client=client))
        self.fsm.receive(_StatusUpdate(configuration=desired, state=state))
        self.fsm.receive(ClusterStatusInputs.SHUTDOWN)
        self.assertEqual((client.transport.disconnecting,
                          self.convergence_loop.inputted[-1]),
                         (True, ConvergenceLoopInputs.STOP))

    def test_shutdown_fsm_ignores_disconnection(self):
        """
        If the FSM has been shutdown it ignores disconnection event.
        """
        client = connected_amp_protocol()
        desired = object()
        state = object()
        self.fsm.receive(_ConnectedToControlService(client=client))
        self.fsm.receive(_StatusUpdate(configuration=desired, state=state))
        self.fsm.receive(ClusterStatusInputs.SHUTDOWN)
        self.fsm.receive(ClusterStatusInputs.DISCONNECTED_FROM_CONTROL_SERVICE)
        self.assertConvergenceLoopInputted([
            _ClientStatusUpdate(client=client, configuration=desired,
                                state=state),
            # This is caused by the shutdown... and the disconnect results
            # in no further messages:
            ConvergenceLoopInputs.STOP])

    def test_shutdown_fsm_ignores_cluster_status(self):
        """
        If the FSM has been shutdown it ignores cluster status update.
        """
        client = connected_amp_protocol()
        desired = object()
        state = object()
        self.fsm.receive(_ConnectedToControlService(client=client))
        self.fsm.receive(ClusterStatusInputs.SHUTDOWN)
        self.fsm.receive(_StatusUpdate(configuration=desired, state=state))
        # We never send anything to convergence loop FSM:
        self.assertConvergenceLoopInputted([])


def no_action():
    """
    Return an ``IStateChange`` that immediately does nothing.
    """
    return ControllableAction(result=succeed(None))


class SleepTests(TestCase):
    """
    Tests for ``_Sleep``.
    """
    def test_jitter(self):
        """
        ``_Sleep.with_jitter`` adds some noise to the given delay.
        """
        base = 100
        delays = [_Sleep.with_jitter(base).delay_seconds for _ in range(3000)]
        # Since we're dealing with random results we can't quite assert
        # deterministically, but we can get some assurance.
        self.assertEqual(
            dict(less_than_max=all(d <= 1.2 * base for d in delays),
                 more_than_min=all(d >= 0.8 * base for d in delays),
                 expected_average=(abs(sum(delays) / 3000.0 - base) < 5),
                 spread=(max(delays) - min(delays)) > 0.2 * base),
            dict(less_than_max=True,
                 more_than_min=True,
                 expected_average=True,
                 spread=True))


class ConvergenceLoopFSMTests(TestCase):
    """
    Tests for FSM created by ``build_convergence_loop_fsm``.
    """
    def test_new_stopped(self):
        """
        A newly created FSM is stopped.
        """
        loop = build_convergence_loop_fsm(
            Clock(), ControllableDeployer(u"192.168.1.1", [], [])
        )
        self.assertEqual(loop.state, ConvergenceLoopStates.STOPPED)

    def test_new_status_update_starts_discovery(self):
        """
        A stopped FSM that receives a status update starts discovery.
        """
        deployer = ControllableDeployer(u"192.168.1.1", [Deferred()], [])
        loop = build_convergence_loop_fsm(Clock(), deployer)
        loop.receive(_ClientStatusUpdate(client=FakeAMPClient(),
                                         configuration=Deployment(),
                                         state=DeploymentState()))
        self.assertEqual(len(deployer.local_states), 0)  # Discovery started

    def make_amp_client(self, local_states, successes=None):
        """
        Create AMP client that can respond successfully to a
        ``NodeStateCommand``.

        :param local_states: The node states we expect to be able to send.
        :param successes: List indicating whether the response to the
            corresponding states should fail.  ``True`` to make a client which
            responds to requests with results, ``False`` to make a client which
            response with failures. Defaults to always succeeding.
        :type successes: ``None`` or ``list`` of ``bool``

        :return FakeAMPClient: Fake AMP client appropriately setup.
        """
        client = FakeAMPClient()
        command = NodeStateCommand
        if successes is None:
            successes = repeat(True)
        for local_state, success in zip(local_states, successes):
            kwargs = dict(state_changes=(local_state,))
            if success:
                client.register_response(
                    command=command, kwargs=kwargs, response={"result": None},
                )
            else:
                client.register_response(
                    command=command, kwargs=kwargs,
                    response=Exception("Simulated request problem"),
                )
        return client

    def assert_discovery_and_send_logged(self, logger):
        """
        Discovery action was logged in context of the convergence iteration
        action.
        """
        discovery = assertHasAction(
            self, logger, LOG_DISCOVERY, True,
            endFields={u"state": NodeLocalState(node_state=self.local_state)})
        convergence = assertHasAction(self, logger, LOG_CONVERGE, True)
        send = assertHasAction(
            self, logger, LOG_SEND_TO_CONTROL_SERVICE, True)
        self.assertIn(discovery, convergence.children)
        self.assertIn(send, convergence.children)

    @capture_logging(assert_discovery_and_send_logged)
    def test_convergence_done_notify(self, logger):
        """
        A FSM doing convergence that gets a discovery result, sends the
        discovered state to the control service using the last received
        client.
        """
        self.local_state = local_state = NodeState(hostname=u"192.0.2.123")
        client = self.make_amp_client([local_state])
        action = ControllableAction(result=succeed(None))
        deployer = ControllableDeployer(
            local_state.hostname, [succeed(local_state)], [action]
        )
        loop = build_convergence_loop_fsm(Clock(), deployer)
        self.patch(loop, "logger", logger)
        loop.receive(
            _ClientStatusUpdate(
                client=client,
                configuration=Deployment(
                    nodes=frozenset([to_node(local_state)])
                ),
                state=DeploymentState(
                    nodes=frozenset([local_state])
                )
            )
        )
        self.assertEqual(client.calls, [(NodeStateCommand,
                                         dict(state_changes=(local_state,)))])

    def test_convergence_done_unchanged_notify(self):
        """
        An FSM doing convergence that discovers state unchanged from the last
        state acknowledged by the control service does not re-send that state.
        """
        local_state = NodeState(hostname=u'192.0.2.123')
        configuration = Deployment(nodes=[to_node(local_state)])
        state = DeploymentState(nodes=[local_state])
        deployer = ControllableDeployer(
            local_state.hostname,
            [succeed(local_state), succeed(local_state.copy())],
            [no_action(), no_action()]
        )
        client = self.make_amp_client([local_state])
        reactor = Clock()
        loop = build_convergence_loop_fsm(reactor, deployer)
        loop.receive(_ClientStatusUpdate(
            client=client, configuration=configuration, state=state))
        reactor.advance(_UNCONVERGED_DELAY)

        # Calculating actions happened, result was run... and then we did
        # whole thing again:
        self.assertEqual(
            (deployer.calculate_inputs, client.calls),
            (
                # Check that the loop has run twice
                [(local_state, configuration, state),
                 (local_state, configuration, state)],
                # But that state was only sent once.
                [(NodeStateCommand, dict(state_changes=(local_state,)))],
            )
        )

    def test_convergence_done_changed_notify(self):
        """
        A FSM doing convergence that gets a discovery result that is changed
        from the last time it sent data does send the discoverd state to
        the control service.
        """
        local_state = NodeState(hostname=u'192.0.2.123')
        changed_local_state = local_state.set(
            applications=pset([Application(
                name=u"app",
                image=DockerImage.from_string(u"nginx"))]),
        )
        configuration = Deployment(nodes=[to_node(local_state)])
        state = DeploymentState(nodes=[local_state])
        changed_state = DeploymentState(nodes=[changed_local_state])
        deployer = ControllableDeployer(
            local_state.hostname,
            [succeed(local_state), succeed(changed_local_state)],
            [no_action(), no_action()])
        client = self.make_amp_client([local_state, changed_local_state])
        reactor = Clock()
        loop = build_convergence_loop_fsm(reactor, deployer)
        loop.receive(_ClientStatusUpdate(
            client=client, configuration=configuration, state=state))
        reactor.advance(_UNCONVERGED_DELAY)

        # Calculating actions happened, result was run... and then we did
        # whole thing again:
        self.assertEqual(
            (deployer.calculate_inputs, client.calls),
            (
                # Check that the loop has run twice
                [(local_state, configuration, state),
                 (changed_local_state, configuration, changed_state)],
                # And the state was sent twice
                [(NodeStateCommand, dict(state_changes=(local_state,))),
                 (NodeStateCommand,
                  dict(state_changes=(changed_local_state,)))],
            )
        )

    def test_convergence_sent_state_fail_resends(self):
        """
        If sending state to the control node fails the next iteration will send
        state even if the state hasn't changed.
        """
        local_state = NodeState(hostname=u'192.0.2.123')
        configuration = Deployment(nodes=[to_node(local_state)])
        state = DeploymentState(nodes=[local_state])
        deployer = ControllableDeployer(
            local_state.hostname,
            [succeed(local_state), succeed(local_state.copy())],
            [no_action(), no_action()])
        client = self.make_amp_client(
            [local_state], successes=[False],
        )
        reactor = Clock()
        loop = build_convergence_loop_fsm(reactor, deployer)
        loop.receive(_ClientStatusUpdate(
            client=client, configuration=configuration, state=state))
        reactor.advance(_UNCONVERGED_DELAY)

        # Calculating actions happened, result was run... and then we did
        # whole thing again:
        self.assertTupleEqual(
            (deployer.calculate_inputs, client.calls),
            (
                # Check that the loop has run twice
                [(local_state, configuration, state),
                 (local_state, configuration, state)],
                # And that state was re-sent even though it remained unchanged
                [(NodeStateCommand, dict(state_changes=(local_state,))),
                 (NodeStateCommand, dict(state_changes=(local_state,)))],
            )
        )

    def test_convergence_sent_state_fail_resends_alternating(self):
        """
        If sending state to the control node fails the next iteration will send
        state even if the state is the same as the last acknowledge state.

        The situation this is intended to model is the following sequence:
        1. Agent sends original state to control node, which records and
           acknowledges it.
        2. Agent sends changed state to control node, which records it, but
           errors out before acknowledging it.
        3. State returns to original state. If we don't clear the acknowledged
           state, the agent won't send a state update, but the control node
           will think the state is still the changed state.
        """
        local_state = NodeState(
            hostname=u'192.0.2.123',
            applications=pset(),
        )
        changed_local_state = local_state.set(
            applications={Application(
                name=u"app",
                image=DockerImage.from_string(u"nginx"))},
        )
        configuration = Deployment(nodes=[to_node(local_state)])
        state = DeploymentState(nodes=[local_state])
        changed_state = DeploymentState(nodes=[changed_local_state])
        deployer = ControllableDeployer(
            local_state.hostname,
            [
                # Discover current state
                succeed(local_state),
                # Discover changed state, this won't be acknowledged
                succeed(changed_local_state),
                # Discover last acknowledge state again.
                succeed(local_state)
            ],
            [no_action(), no_action(), no_action()])
        client = self.make_amp_client(
            [local_state, changed_local_state],
            # local_state will be acknowledge
            # changed_local_state will result in an error.
            successes=[True, False],
        )
        reactor = Clock()
        loop = build_convergence_loop_fsm(reactor, deployer)
        loop.receive(_ClientStatusUpdate(
            client=client, configuration=configuration, state=state))

        # Wait for all three iterations to occur.
        reactor.advance(_UNCONVERGED_DELAY)
        reactor.advance(_UNCONVERGED_DELAY * _UNCONVERGED_BACKOFF_FACTOR)

        # Calculating actions happened, result was run... and then we did
        # whole thing again:
        self.assertTupleEqual(
            (deployer.calculate_inputs, client.calls),
            (
                # Check that the loop has run thrice
                [(local_state, configuration, state),
                 (changed_local_state, configuration, changed_state),
                 (local_state, configuration, state)],
                # And that state was re-sent even though it matched the last
                # acknowledged state
                [(NodeStateCommand, dict(state_changes=(local_state,))),
                 (NodeStateCommand,
                  dict(state_changes=(changed_local_state,))),
                 (NodeStateCommand, dict(state_changes=(local_state,)))],
            )
        )

    @validate_logging(assertHasMessage, LOG_CALCULATED_ACTIONS)
    def test_convergence_done_update_local_state(self, logger):
        """
        An FSM doing convergence that gets a discovery result supplies an
        updated ``cluster_state`` to ``calculate_necessary_state_changes``.
        """
        local_node_hostname = u'192.0.2.123'
        # Control service reports that this node has no manifestations.
        received_node = NodeState(hostname=local_node_hostname)
        received_cluster_state = DeploymentState(nodes=[received_node])
        discovered_manifestation = Manifestation(
            dataset=Dataset(dataset_id=uuid4()),
            primary=True
        )
        local_node_state = NodeState(
            hostname=local_node_hostname,
            manifestations={discovered_manifestation.dataset_id:
                            discovered_manifestation},
            devices={}, paths={},
        )
        client = self.make_amp_client([local_node_state])
        action = ControllableAction(result=Deferred())
        deployer = ControllableDeployer(
            local_node_hostname, [succeed(local_node_state)], [action]
        )

        fsm = build_convergence_loop_fsm(Clock(), deployer)
        self.patch(fsm, "logger", logger)
        fsm.receive(
            _ClientStatusUpdate(
                client=client,
                # Configuration is unimportant here, but we are recreating a
                # situation where the local state now matches the desired
                # configuration but the control service is not yet aware that
                # convergence has been reached.
                configuration=Deployment(nodes=[to_node(local_node_state)]),
                state=received_cluster_state
            )
        )

        expected_local_cluster_state = DeploymentState(
            nodes=[local_node_state])
        [calculate_necessary_state_changes_inputs] = deployer.calculate_inputs

        (_, _, actual_cluster_state) = calculate_necessary_state_changes_inputs

        self.assertEqual(expected_local_cluster_state, actual_cluster_state)

    def test_convergence_done_changes(self):
        """
        A FSM doing convergence that gets a discovery result starts applying
        calculated changes using last received desired configuration and
        cluster state.
        """
        local_state = NodeState(hostname=u'192.0.2.123')
        configuration = Deployment()
        received_state = DeploymentState(nodes=[])
        # Since this Deferred is unfired we never proceed to next
        # iteration; if we did we'd get exception from discovery since we
        # only configured one discovery result.
        action = ControllableAction(result=Deferred())
        deployer = ControllableDeployer(
            local_state.hostname, [succeed(local_state)], [action]
        )
        loop = build_convergence_loop_fsm(Clock(), deployer)
        loop.receive(_ClientStatusUpdate(
            client=self.make_amp_client([local_state]),
            configuration=configuration, state=received_state))

        expected_local_state = DeploymentState(nodes=[local_state])

        # Calculating actions happened, and result was run:
        self.assertEqual(
            (deployer.calculate_inputs, action.called),
            ([(local_state, configuration, expected_local_state)], True))

    def assert_full_logging(self, logger):
        """
        A convergence action is logged inside the finite state maching
        logging.
        """
        transition = assertHasAction(self, logger, LOG_FSM_TRANSITION, True)
        converge = assertHasAction(
            self, logger, LOG_CONVERGE, True,
            {u"cluster_state": self.cluster_state,
             u"desired_configuration": self.configuration})
        self.assertIn(converge, transition.children)
        send = assertHasAction(self, logger, LOG_SEND_TO_CONTROL_SERVICE, True,
                               {u"local_changes": [self.local_state]})
        self.assertIn(send, converge.children)
        calculate = assertHasMessage(
            self, logger, LOG_CALCULATED_ACTIONS,
            {u"calculated_actions": self.action})
        self.assertIn(calculate, converge.children)

    @validate_logging(assert_full_logging)
    def convergence_iteration(
            self, logger,
            initial_action=ControllableAction(result=succeed(None)),
            later_actions=[ControllableAction(result=succeed(None)),
                           ControllableAction(result=succeed(None))]):
        """
        Do one iteration of a convergence loop.

        :param initial_action: First ``IStateChange`` provider to
            calculate as necessary action.
        :param later_actions: List of ``IStateChange``, to be returned
            second and third times discovery is done, i.e. after first
            iteration.

        :return: ``ConvergenceLoop`` in SLEEPING state.
        """
        self.local_state = local_state = NodeState(hostname=u'192.0.2.123')
        self.configuration = configuration = Deployment()
        self.cluster_state = received_state = DeploymentState(nodes=[])
        self.action = initial_action
        # We only support discovery twice; anything more will result in
        # exception being thrown:
        self.deployer = deployer = ControllableDeployer(
            local_state.hostname, [succeed(local_state), succeed(local_state)],
            [initial_action] + later_actions,
        )
        client = self.make_amp_client([local_state])
        self.reactor = reactor = Clock()
        loop = build_convergence_loop_fsm(reactor, deployer)
        self.patch(loop, "logger", logger)
        loop.receive(_ClientStatusUpdate(
            client=client, configuration=configuration, state=received_state))

        expected_cluster_state = DeploymentState(
            nodes=[local_state])

        # Only one iteration of the covergence loop was run.
        self.assertTupleEqual(
            (deployer.calculate_inputs, client.calls),
            ([(local_state, configuration, expected_cluster_state)],
             [(NodeStateCommand, dict(state_changes=(local_state,)))])
        )
        self.assertEqual(loop.state, ConvergenceLoopStates.SLEEPING)
        return loop

    def test_convergence_done_delays_new_iteration(self):
        """
        An FSM completing the changes from one convergence iteration doesn't
        instantly start another iteration.
        """
        self.convergence_iteration()

    def test_convergence_iteration_sleeping_stop(self):
        """
        When a convergence loop in the sleeping state receives a STOP the loop
        stops.
        """
        loop = self.convergence_iteration()
        loop.receive(ConvergenceLoopInputs.STOP)
        # Stopped with no scheduled calls left hanging:
        self.assertEqual(
            dict(state=loop.state, calls=self.reactor.getDelayedCalls()),
            dict(state=ConvergenceLoopStates.STOPPED, calls=[]))

    def test_convergence_iteration_status_update_no_consequences(self):
        """
        When a convergence loop in the sleeping state receives a status update
        the next iteration of the event loop uses it. The event loop is
        not woken up if the update would not result in newly calculated
        required actions.
        """
        # Later calculations will return a NoOp(), indicating no need to
        # wake up:
        loop = self.convergence_iteration(later_actions=[NO_OP, NO_OP])
        node_state = NodeState(hostname=u'192.0.3.5')
        changed_configuration = Deployment(
            nodes=frozenset([to_node(node_state)]))
        changed_state = DeploymentState(
            nodes=[node_state, self.local_state])

        # An update received while sleeping:
        loop.receive(_ClientStatusUpdate(
            client=self.make_amp_client([self.local_state]),
            configuration=changed_configuration, state=changed_state))
        num_calculations_pre_sleep = len(self.deployer.calculate_inputs)

        # Action finally finishes, and we can move on to next iteration,
        # but only after sleeping.
        self.reactor.advance(_UNCONVERGED_DELAY)
        num_calculations_after_sleep = len(self.deployer.calculate_inputs)
        self.assertEqual(
            dict(pre=num_calculations_pre_sleep,
                 post=num_calculations_after_sleep),
            dict(pre=2,  # initial calculate, extra calculate on delivery
                 post=3)  # the above plus next iteration
        )

    def test_status_update_while_sleeping_no_discovery(self):
        """
        When an update is received while the convergence loop is sleeping, we
        don't want any discovery to happen since that will lead to load on
        external resources.
        """
        # Later calculations will return a NoOp(), indicating no need to
        # wake up:
        loop = self.convergence_iteration(later_actions=[NO_OP, NO_OP])
        remaining_discover_calls = len(self.deployer.local_states)

        # An update received while sleeping:
        loop.receive(_ClientStatusUpdate(
            client=self.make_amp_client([self.local_state]),
            configuration=self.configuration, state=self.cluster_state))
        # No additional discovery done due to update:
        self.assertEqual(
            remaining_discover_calls - len(self.deployer.local_states),
            0)

    def test_longer_sleep_when_converged(self):
        """
        When a convergence loop results in a ``NoOp`` the sleep is based on
        that configured in the returned NoOp.
        """
        loop = self.convergence_iteration(initial_action=NO_OP,
                                          later_actions=[NO_OP, NO_OP])

        # An update received while sleeping:
        loop.receive(_ClientStatusUpdate(
            client=self.make_amp_client([self.local_state]),
            configuration=self.configuration, state=self.cluster_state))

        # No additional discovery done due to update:
        pre_sleep = len(self.deployer.local_states)

        [delayed_call] = self.reactor.getDelayedCalls()
        delay = delayed_call.getTime() - self.reactor.seconds()

        # Sleep until 50ms before wakeup point, so we should still be
        # sleeping:
        self.reactor.advance(delay - 0.05)
        mid_sleep = len(self.deployer.local_states)

        # Sleep until right after event happens, with extra bit of sleep
        # to ensure we don't break on floating point rounding errors:
        self.reactor.advance(0.051)
        post_sleep = len(self.deployer.local_states)

        self.assertEqual(
            dict(long_enough=(delay > 200),
                 pre=pre_sleep, mid=mid_sleep, post=post_sleep),
            dict(long_enough=True,  # NO_OP has 300s sleep with jitter added
                 pre=1,  # no new iteration yet
                 mid=1,  # slept not quite enough, so still no new iteration
                 post=0),  # slept full poll interval, new iteration
        )

    def test_shorter_sleep(self):
        """
        When a sleeping convergence loop gets an update and sees if it should
        wake up, if the result is a ``NoOp`` with a shorter remaining
        duration the sleep is appropriately shortened.
        """
        loop = self.convergence_iteration(
            initial_action=NO_OP,
            later_actions=[NoOp(sleep=timedelta(seconds=17))])

        # An update received while sleeping:
        loop.receive(_ClientStatusUpdate(
            client=self.make_amp_client([self.local_state]),
            configuration=self.configuration, state=self.cluster_state))

        [delayed_call] = self.reactor.getDelayedCalls()
        delay = delayed_call.getTime() - self.reactor.seconds()
        self.assertEqual(delay, 17)

    def assert_woken_up(self, loop):
        """
        When a new configuraton and cluster state are fed to a sleeping
        convergence loop which would cause newly calculated actions, the
        loop wakes up and does another iteration.

        :param loop: A ``ConvergenceLoop`` in SLEEPING state.
        """
        node_state = NodeState(hostname=u'192.0.3.5')
        changed_configuration = Deployment(
            nodes=frozenset([to_node(node_state)]))
        changed_state = DeploymentState(
            nodes=[node_state, self.local_state])
        # An update received while sleeping:
        loop.receive(_ClientStatusUpdate(
            client=self.make_amp_client([self.local_state]),
            configuration=changed_configuration, state=changed_state))
        # Update resulted in waking up and starting new iteration:
        self.assertEqual(
            dict(remaining_discoveries=len(self.deployer.local_states),
                 number_calculates=len(self.deployer.calculate_inputs),
                 calculate_inputs=self.deployer.calculate_inputs[-1]),
            dict(remaining_discoveries=0,  # used up both, one per iteration
                 number_calculates=3,  # one per iteration, one on on wakeup
                 # We used new config/cluster state in latest iteration:
                 calculate_inputs=(
                     self.local_state, changed_configuration, changed_state)))

    def test_convergence_iteration_status_update_wakeup(self):
        """
        When a convergence loop in the sleeping state receives a status update
        the next iteration of the event loop uses it. The event loop is
        woken up if the update results in newly calculated required
        actions.
        """
        loop = self.convergence_iteration()
        self.assert_woken_up(loop)

    @capture_logging(lambda self, logger:
                     self.assertEqual(
                         len(logger.flushTracebacks(CustomException)), 1))
    def test_convergence_iteration_status_update_wakeup_error(self, logger):
        """
        When a convergence loop in the sleeping state receives a status update
        the next iteration of the event loop uses it. The event loop is
        woken up if the update results in an exception, on the theory that
        given lack of accurate information we should err on the side of
        being more responsive.
        """
        loop = self.convergence_iteration()

        # Fail to calculate next time around, when we're deciding whether
        # to wake up:
        self.deployer.calculated_actions[0] = CustomException()
        self.assert_woken_up(loop)

    def test_convergence_done_delays_new_iteration_ack(self):
        """
        A state update isn't sent if the control node hasn't acknowledged the
        last state update.
        """
        self.local_state = local_state = NodeState(hostname=u'192.0.2.123')
        self.configuration = configuration = Deployment()
        self.cluster_state = received_state = DeploymentState(nodes=[])
        self.action = action = ControllableAction(result=succeed(None))
        deployer = ControllableDeployer(
            local_state.hostname, [succeed(local_state)], [action]
        )
        client = self.make_amp_client([local_state])
        reactor = Clock()
        loop = build_convergence_loop_fsm(reactor, deployer)
        loop.receive(_ClientStatusUpdate(
            # We don't want to receive the acknowledgment of the
            # state update.
            client=DelayedAMPClient(client),
            configuration=configuration,
            state=received_state))

        # Wait for the delay in the convergence loop to pass.  This won't do
        # anything, since we are also waiting for state to be acknowledged.
        reactor.advance(_UNCONVERGED_DELAY)

        # Only one status update was sent.
        self.assertListEqual(
            client.calls,
            [(NodeStateCommand, dict(state_changes=(local_state,)))],
        )

    @validate_logging(lambda test_case, logger: test_case.assertEqual(
        len(logger.flush_tracebacks(RuntimeError)), 1))
    def test_convergence_error_start_new_iteration(self, logger):
        """
        Even if the convergence fails, a new iteration is started anyway.
        """
        local_state = NodeState(hostname=u'192.0.2.123')
        configuration = Deployment(nodes=frozenset([to_node(local_state)]))
        state = DeploymentState(nodes=[local_state])
        action = ControllableAction(result=fail(RuntimeError("Failed action")))
        # First discovery succeeds, leading to failing action; second
        # discovery will just wait for Deferred to fire. Thus we expect to
        # finish test in discovery state.
        deployer = ControllableDeployer(
            local_state.hostname,
            [succeed(local_state), Deferred()],
            [action])
        client = self.make_amp_client([local_state])
        reactor = Clock()
        loop = build_convergence_loop_fsm(reactor, deployer)
        self.patch(loop, "logger", logger)
        loop.receive(_ClientStatusUpdate(
            client=client, configuration=configuration, state=state))
        reactor.advance(_UNCONVERGED_DELAY)
        # Calculating actions happened, result was run and caused error...
        # but we started on loop again and are thus in discovery state,
        # which we can tell because all faked local states have been
        # consumed:
        self.assertEqual(len(deployer.local_states), 0)

    def _discover_state_error_test(self, logger, error):
        """
        Verify that an error from ``IDeployer.discover_state`` does not prevent
        a subsequent loop iteration from re-trying state discovery.

        :param logger: The ``MemoryLogger`` where log messages are going.
        :param error: The first state to pass to the
            ``ControllableDeployer``, a ``CustomException`` or a ``Deferred``
            that fails with ``CustomException``.
        """
        local_state = NodeState(hostname=u"192.0.1.2")
        configuration = Deployment(nodes=frozenset([to_node(local_state)]))
        state = DeploymentState(nodes=[local_state])

        client = self.make_amp_client([local_state])
        local_states = [error, succeed(local_state)]

        actions = [no_action(), no_action()]
        deployer = ControllableDeployer(
            hostname=local_state.hostname,
            local_states=local_states,
            calculated_actions=actions,
        )
        reactor = Clock()
        loop = build_convergence_loop_fsm(reactor, deployer)
        self.patch(loop, "logger", logger)

        loop.receive(_ClientStatusUpdate(
            client=client, configuration=configuration, state=state))
        reactor.advance(_UNCONVERGED_DELAY)

        # If the loop kept running then the good state following the error
        # state should have been sent via the AMP client on a subsequent
        # iteration.
        self.assertEqual(
            [(NodeStateCommand, dict(state_changes=(local_state,)))],
            client.calls
        )

    def _assert_simulated_error(self, logger):
        """
        Verify that the error used by ``_discover_state_error_test`` has been
        logged to ``logger``.
        """
        self.assertEqual(len(logger.flush_tracebacks(CustomException)), 1)

    @validate_logging(_assert_simulated_error)
    def test_discover_state_async_error_start_new_iteration(self, logger):
        """
        If the discovery of local state fails with a ``Deferred`` that fires
        with a ``Failure``, a new iteration is started anyway.
        """
        self._discover_state_error_test(logger, fail(CustomException()))

    @validate_logging(_assert_simulated_error)
    def test_discover_state_sync_error_start_new_iteration(self, logger):
        """
        If the discovery of local state raises a synchronous exception, a new
        iteration is started anyway.
        """
        self._discover_state_error_test(logger, CustomException())

    def test_convergence_status_update(self):
        """
        A FSM doing convergence that receives a status update stores the
        client, desired configuration and cluster state, which are then
        used in next convergence iteration.
        """
        local_state = NodeState(hostname=u'192.0.2.123')
        local_state2 = NodeState(hostname=u'192.0.2.123')
        configuration = Deployment(nodes=frozenset([to_node(local_state)]))
        state = DeploymentState(nodes=[local_state])
        # Until this Deferred fires the first iteration won't finish:
        action = ControllableAction(result=Deferred())
        # Until this Deferred fires the second iteration won't finish:
        action2 = ControllableAction(result=Deferred())
        deployer = ControllableDeployer(
            local_state.hostname,
            [succeed(local_state), succeed(local_state2)],
            [action, action2])
        client = self.make_amp_client([local_state])
        reactor = Clock()
        loop = build_convergence_loop_fsm(reactor, deployer)
        loop.receive(_ClientStatusUpdate(
            client=client, configuration=configuration, state=state))

        # Calculating actions happened, action is run, but waits for
        # Deferred to be fired... Meanwhile a new status update appears!
        client2 = self.make_amp_client([local_state2])
        configuration2 = Deployment(nodes=frozenset([to_node(local_state)]))
        state2 = DeploymentState(nodes=[local_state])
        loop.receive(_ClientStatusUpdate(
            client=client2, configuration=configuration2, state=state2))
        # Action finally finishes, and we can move on to next iteration,
        # which happens with second set of client, desired configuration
        # and cluster state:
        action.result.callback(None)
        reactor.advance(_UNCONVERGED_DELAY)

        self.assertTupleEqual(
            (deployer.calculate_inputs, client.calls, client2.calls),
            ([(local_state, configuration, state),
              (local_state2, configuration2, state2)],
             [(NodeStateCommand, dict(state_changes=(local_state,)))],
             [(NodeStateCommand, dict(state_changes=(local_state2,)))]))

    def test_convergence_stop(self):
        """
        A FSM doing convergence that receives a stop input stops when the
        convergence iteration finishes.
        """
        local_state = NodeState(hostname=u'192.0.2.123')
        configuration = Deployment(nodes=frozenset([to_node(local_state)]))
        state = DeploymentState(nodes=[local_state])

        # Until this Deferred fires the first iteration won't finish:
        action = ControllableAction(result=Deferred())
        # Only one discovery result is configured, so a second attempt at
        # discovery would fail:
        deployer = ControllableDeployer(
            local_state.hostname, [succeed(local_state)],
            [action]
        )
        client = self.make_amp_client([local_state])
        reactor = Clock()
        loop = build_convergence_loop_fsm(reactor, deployer)
        loop.receive(_ClientStatusUpdate(
            client=client, configuration=configuration, state=state))

        # Calculating actions happened, action is run, but waits for
        # Deferred to be fired... Meanwhile a stop input is received!
        loop.receive(ConvergenceLoopInputs.STOP)
        # Action finally finishes:
        action.result.callback(None)
        reactor.advance(_UNCONVERGED_DELAY)

        # work is scheduled:
        expected = (
            # The actions are calculated
            [(local_state, configuration, state)],
            # And the result is run
            [(NodeStateCommand, dict(state_changes=(local_state,)))],
            # The state machine gets to the desired state.
            ConvergenceLoopStates.STOPPED,
            # And no subsequent work is scheduled to be run.
            [],
        )
        actual = (
            deployer.calculate_inputs,
            client.calls,
            loop.state,
            reactor.getDelayedCalls(),
        )
        self.assertTupleEqual(expected, actual)

    def test_convergence_stop_then_status_update(self):
        """
        A FSM doing convergence that receives a stop input and then a status
        update continues on to next convergence iteration (i.e. stop
        ends up being ignored).

        Note: A stop input implies that the client has changed.
        """
        local_state = NodeState(hostname=u'192.0.2.123')
        local_state2 = NodeState(hostname=u'192.0.2.123')
        configuration = Deployment(nodes=frozenset([to_node(local_state)]))
        state = DeploymentState(nodes=[local_state])

        # Until this Deferred fires the first iteration won't finish:
        action = ControllableAction(result=Deferred())
        # Until this Deferred fires the second iteration won't finish:
        action2 = ControllableAction(result=Deferred())
        deployer = ControllableDeployer(
            local_state.hostname,
            [succeed(local_state), succeed(local_state2)],
            [action, action2]
        )
        client = self.make_amp_client([local_state])
        reactor = Clock()
        loop = build_convergence_loop_fsm(reactor, deployer)
        loop.receive(_ClientStatusUpdate(
            client=client, configuration=configuration, state=state))

        # Calculating actions happened, action is run, but waits for
        # Deferred to be fired... Meanwhile a new status update appears!
        client2 = self.make_amp_client([local_state2])
        configuration2 = Deployment(nodes=frozenset([to_node(local_state)]))
        state2 = DeploymentState(nodes=[local_state])
        loop.receive(ConvergenceLoopInputs.STOP)
        # And then another status update!
        loop.receive(_ClientStatusUpdate(
            client=client2, configuration=configuration2, state=state2))
        # Action finally finishes, and we can move on to next iteration,
        # which happens with second set of client, desired configuration
        # and cluster state:
        action.result.callback(None)
        reactor.advance(_UNCONVERGED_DELAY)
        self.assertTupleEqual(
            (deployer.calculate_inputs, client.calls, client2.calls),
            ([(local_state, configuration, state),
              (local_state2, configuration2, state2)],
             [(NodeStateCommand, dict(state_changes=(local_state,)))],
             [(NodeStateCommand, dict(state_changes=(local_state2,)))]))

    def test_discover_states_gets_cluster_state(self):
        """
        ``IDeployer.discover_state`` gets passed the entire cluster state.
        """
        cluster_state = DeploymentState(nodes={
            NodeState(uuid=uuid4(), hostname=u"192.168.1.1"),
        })
        deployer = ControllableDeployer(u"192.168.1.1", [Deferred()], [])
        loop = build_convergence_loop_fsm(Clock(), deployer)
        loop.receive(_ClientStatusUpdate(client=FakeAMPClient(),
                                         configuration=Deployment(),
                                         state=cluster_state))
        self.assertEqual(
            deployer.discover_inputs,
            [(cluster_state, PersistentState())],
        )


class UpdateNodeEraLocator(CommandLocator):
    """
    An AMP locator that can handle the ``SetNodeEraCommand`` AMP command.
    """
    uuid = None
    era = None

    @SetNodeEraCommand.responder
    def set_node_era(self, era, node_uuid):
        self.era = era
        self.uuid = node_uuid
        return {}


class AgentLoopServiceTests(TestCase):
    """
    Tests for ``AgentLoopService``.
    """
    def setUp(self):
        super(AgentLoopServiceTests, self).setUp()
        self.deployer = ControllableDeployer(u"127.0.0.1", [], [])
        self.reactor = MemoryReactorClock()
        self.service = AgentLoopService(
            reactor=self.reactor, deployer=self.deployer, host=u"example.com",
            port=1234, context_factory=ClientContextFactory(), era=uuid4())
        self.node_state = NodeState(uuid=self.deployer.node_uuid,
                                    hostname=self.deployer.hostname)

    def test_start_service(self):
        """
        Starting the service starts a reconnecting TCP client to given host
        and port which calls ``build_agent_client`` with the service when
        connected.
        """
        service = self.service
        service.startService()
        host, port, factory = self.reactor.tcpClients[0][:3]
        protocol = factory.buildProtocol(None)
        self.assertEqual((host, port, factory.__class__,
                          service.reconnecting_factory.__class__,
                          service.reconnecting_factory.continueTrying,
                          protocol.__class__,
                          protocol.wrappedProtocol.__class__,
                          service.running),
                         (u"example.com", 1234, TLSMemoryBIOFactory,
                          ReconnectingClientFactory,
                          True, TLSMemoryBIOProtocol, AgentAMP, True))

    def test_stop_service(self):
        """
        Stopping the service stops the reconnecting TCP client and inputs
        shutdown event to the cluster status FSM.
        """
        service = self.service
        service.cluster_status = fsm = StubFSM()
        service.startService()
        service.stopService()
        self.assertEqual((service.reconnecting_factory.continueTrying,
                          fsm.inputted, service.running),
                         (False, [ClusterStatusInputs.SHUTDOWN], False))

    def test_connected(self):
        """
        When ``connnected()`` is called a ``_ConnectedToControlService`` input
        is passed to the cluster status FSM.
        """
        service = self.service
        service.cluster_status = fsm = StubFSM()
        client = connected_amp_protocol()
        service.connected(client)
        self.assertEqual(fsm.inputted,
                         [_ConnectedToControlService(client=client)])

    def test_send_era_on_connect(self):
        """
        Upon connecting a ``SetNodeEraCommand`` is sent with the current
        node's era and UUID.
        """
        client = AgentAMP(self.reactor, self.service)
        # The object that processes incoming AMP commands:
        server_locator = UpdateNodeEraLocator()
        server = AMP(locator=server_locator)
        pump = connectedServerAndClient(lambda: client, lambda: server)[2]
        pump.flush()
        self.assertEqual(
            # Actual result of handling AMP commands, if any:
            dict(era=server_locator.era, uuid=server_locator.uuid),
            # Expected result:
            dict(era=unicode(self.service.era),
                 uuid=unicode(self.deployer.node_uuid)))

    def test_connected_resets_factory_delay(self):
        """
        When ``connected()`` is called the reconnect delay on the client
        factory is reset.
        """
        factory = self.service.reconnecting_factory
        # A series of retries have caused the delay to grow (so that we
        # don't hammer the server with reconnects):
        factory.delay += 500000
        # But now we successfully connect!
        client = connected_amp_protocol()
        self.service.connected(client)
        self.assertEqual(factory.delay, factory.initialDelay)

    def test_disconnected(self):
        """
        When ``connnected()`` is called a
        ``ClusterStatusInputs.DISCONNECTED_FROM_CONTROL_SERVICE`` input is
        passed to the cluster status FSM.
        """
        service = self.service
        service.cluster_status = fsm = StubFSM()
        service.disconnected()
        self.assertEqual(
            fsm.inputted,
            [ClusterStatusInputs.DISCONNECTED_FROM_CONTROL_SERVICE])

    def test_cluster_updated(self):
        """
        When ``cluster_updated()`` is called a ``_StatusUpdate`` input is
        passed to the cluster status FSM.
        """
        service = self.service
        service.cluster_status = fsm = StubFSM()
        config = Deployment()
        state = DeploymentState(
            nodes=[self.node_state],
            node_uuid_to_era={self.deployer.node_uuid: self.service.era})
        service.cluster_updated(config, state)
        self.assertEqual(fsm.inputted, [_StatusUpdate(configuration=config,
                                                      state=state)])

    def test_cluster_updated_wrong_era(self):
        """
        The ``NodeState`` for the local node is removed from the update if the
        era doesn't match this node's actual era.
        """
        service = self.service
        service.cluster_status = fsm = StubFSM()
        config = Deployment()
        state = DeploymentState(
            nodes=[self.node_state],
            node_uuid_to_era={self.deployer.node_uuid: uuid4()})
        service.cluster_updated(config, state)
        self.assertEqual(fsm.inputted,
                         [_StatusUpdate(configuration=config,
                                        state=state.set(nodes=[]))])


def _build_service(test):
    """
    Fixture for creating ``AgentLoopService``.
    """
    service = AgentLoopService(
        reactor=MemoryReactorClock(),
        deployer=ControllableDeployer(u"127.0.0.1", [], []),
        host=u"example.com", port=1234,
        context_factory=ClientContextFactory(), era=uuid4())
    service.cluster_status = StubFSM()
    return service


class AgentLoopServiceInterfaceTests(
        iconvergence_agent_tests_factory(_build_service)):
    """
    ``IConvergenceAgent`` tests for ``AgentLoopService``.
    """


def make_remotestatepersister(test_case):
    """
    Create a ``RemoteStatePersister`` for use in tests.

    :return: ``tuple`` of ``IStatePersiter`` and 0-argument callable returning
    a ``PersistentState``.
    """
    clock = Clock()
    control_amp_service, client = make_loopback_control_client(
        test_case,
        reactor=clock,
    )
    persistence_service = control_amp_service.configuration_service
    return RemoteStatePersister(client=client), (
        lambda: persistence_service.get().persistent_state
    )


class RemoteStatePersisterTests(
    make_istatepersister_tests(make_remotestatepersister)
):
    """
    Tests for ``RemoteStatePersister``.
    """


class UncovergedDelayTests(TestCase):
    """
    Tests for ``_UnconvergedDelay``.
    """

    @given(floats())
    def test_first_is_min_sleep(self, duration):
        """
        The first call to `sleep` uses `min_sleep` duration.
        """
        assume(not math.isnan(duration))
        delay = _UnconvergedDelay(min_sleep=duration)
        sleep = delay.sleep()
        self.assertEqual(duration, sleep.delay_seconds)

    def test_second_uses_backoff(self):
        """
        The second call to `sleep` adjusts by `_UNCONVERGED_BACKOFF_FACTOR`.
        """
        min_sleep = 0.1
        delay = _UnconvergedDelay(min_sleep=min_sleep)
        delay.sleep()
        sleep = delay.sleep()
        self.assertEqual(
            min_sleep * _UNCONVERGED_BACKOFF_FACTOR, sleep.delay_seconds)

    def test_limits_at_max_sleep(self):
        """
        The backoff doesn't exceed `max_sleep`.
        """
        min_sleep = 0.1
        max_sleep = 0.2
        delay = _UnconvergedDelay(min_sleep=min_sleep, max_sleep=max_sleep)
        delay.sleep()
        sleep = delay.sleep()
        self.assertEqual(max_sleep, sleep.delay_seconds)

    def test_reset_resets(self):
        """
        `reset_delay` means the next `sleep` returns `min_sleep` duration.
        """
        min_sleep = 0.1
        delay = _UnconvergedDelay(min_sleep=min_sleep)
        delay.sleep()
        delay.reset_delay()
        sleep = delay.sleep()
        self.assertEqual(min_sleep, sleep.delay_seconds)
