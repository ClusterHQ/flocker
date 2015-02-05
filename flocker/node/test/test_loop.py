# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for ``flocker.node._loop``.
"""

from zope.interface import implementer

from twisted.trial.unittest import SynchronousTestCase
from twisted.test.proto_helpers import StringTransport
from twisted.internet.protocol import Protocol
from twisted.internet.defer import succeed, Deferred

from ...testtools import FakeAMPClient
from .._loop import (
    build_cluster_status_fsm, ClusterStatusInputs, _ClientStatusUpdate,
    _StatusUpdate, _ClientConnected, ConvergenceLoopInputs,
    ConvergenceLoopStates, build_convergence_loop_fsm,
    )
from .._deploy import IDeployer, IStateChange
from ...control._protocol import NodeStateCommand


def build_protocol():
    """
    :return: ``Protocol`` hooked up to transport.
    """
    p = Protocol()
    p.makeConnection(StringTransport())
    return p


class StubFSM(object):
    """
    A finite state machine look-alike that just records inputs.
    """
    def __init__(self):
        self.inputted = []

    def receive(self, symbol):
        self.inputted.append(symbol)


class ClusterStatusFSMTests(SynchronousTestCase):
    """
    Tests for the cluster status FSM.
    """
    def setUp(self):
        self.agent_operation = StubFSM()
        self.fsm = build_cluster_status_fsm(self.agent_operation)

    def assertConvergenceLoopInputted(self, expected):
        """
        Assert that that given set of symbols were input to the agent
        operation FSM.
        """
        self.assertEqual(self.agent_operation.inputted, expected)

    def test_creation_no_side_effects(self):
        """
        Creating the FSM has no side effects.
        """
        self.assertConvergenceLoopInputted([])

    def test_first_status_update(self):
        """
        Once the client has been connected and a status update received it
        notifies the agent operation FSM of this.
        """
        client = object()
        desired = object()
        state = object()
        self.fsm.receive(_ClientConnected(client=client))
        self.fsm.receive(_StatusUpdate(configuration=desired, state=state))
        self.assertConvergenceLoopInputted(
            [_ClientStatusUpdate(client=client, configuration=desired,
                                 state=state)])

    def test_second_status_update(self):
        """
        Further status updates are also passed to the agent operation FSM.
        """
        client = object()
        desired1 = object()
        state1 = object()
        desired2 = object()
        state2 = object()
        self.fsm.receive(_ClientConnected(client=client))
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
        client = build_protocol()
        self.fsm.receive(_ClientConnected(client=client))
        self.fsm.receive(_StatusUpdate(configuration=object(),
                                       state=object()))
        self.assertFalse(client.transport.disconnecting)

    def test_disconnect_before_status_update(self):
        """
        If the client disconnects before a status update is received then no
        notification is needed for agent operation FSM.
        """
        self.fsm.receive(_ClientConnected(client=build_protocol()))
        self.fsm.receive(ClusterStatusInputs.CLIENT_DISCONNECTED)
        self.assertConvergenceLoopInputted([])

    def test_disconnect_after_status_update(self):
        """
        If the client disconnects after a status update is received then the
        agent operation is FSM is notified.
        """
        client = object()
        desired = object()
        state = object()
        self.fsm.receive(_ClientConnected(client=client))
        self.fsm.receive(_StatusUpdate(configuration=desired, state=state))
        self.fsm.receive(ClusterStatusInputs.CLIENT_DISCONNECTED)
        self.assertConvergenceLoopInputted(
            [_ClientStatusUpdate(client=client, configuration=desired,
                                 state=state),
             ConvergenceLoopInputs.STOP])

    def test_status_update_after_reconnect(self):
        """
        If the client disconnects, reconnects, and a new status update is
        received then the agent operation FSM is notified.
        """
        client = object()
        desired = object()
        state = object()
        self.fsm.receive(_ClientConnected(client=client))
        self.fsm.receive(_StatusUpdate(configuration=desired, state=state))
        self.fsm.receive(ClusterStatusInputs.CLIENT_DISCONNECTED)
        client2 = object()
        desired2 = object()
        state2 = object()
        self.fsm.receive(_ClientConnected(client=client2))
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
        client = build_protocol()
        self.fsm.receive(_ClientConnected(client=client))
        self.fsm.receive(ClusterStatusInputs.SHUTDOWN)
        self.assertEqual((client.transport.disconnecting,
                          self.agent_operation.inputted),
                         (True, []))

    def test_shutdown_after_status_update(self):
        """
        If the FSM is shutdown after connection and status update is received
        then it disconnects and also notifys the agent operation FSM that
        is should stop.
        """
        client = build_protocol()
        desired = object()
        state = object()
        self.fsm.receive(_ClientConnected(client=client))
        self.fsm.receive(_StatusUpdate(configuration=desired, state=state))
        self.fsm.receive(ClusterStatusInputs.SHUTDOWN)
        self.assertEqual((client.transport.disconnecting,
                          self.agent_operation.inputted[-1]),
                         (True, ConvergenceLoopInputs.STOP))

    def test_shutdown_fsm_ignores_disconnection(self):
        """
        If the FSM has been shutdown it ignores disconnection event.
        """
        client = build_protocol()
        desired = object()
        state = object()
        self.fsm.receive(_ClientConnected(client=client))
        self.fsm.receive(_StatusUpdate(configuration=desired, state=state))
        self.fsm.receive(ClusterStatusInputs.SHUTDOWN)
        self.fsm.receive(ClusterStatusInputs.CLIENT_DISCONNECTED)
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
        client = build_protocol()
        desired = object()
        state = object()
        self.fsm.receive(_ClientConnected(client=client))
        self.fsm.receive(ClusterStatusInputs.SHUTDOWN)
        self.fsm.receive(_StatusUpdate(configuration=desired, state=state))
        # We never send anything to agent operation FSM:
        self.assertConvergenceLoopInputted([])


@implementer(IStateChange)
class ControllableAction(object):
    """
    ``IStateChange`` whose results can be controlled.
    """
    def __init__(self, result):
        self.result = result
        self.called = False
        self.deployer = None

    def run(self, deployer):
        self.called = True
        self.deployer = deployer
        return self.result


@implementer(IDeployer)
class ControllableDeployer(object):
    """
    ``IDeployer`` whose results can be controlled.
    """
    def __init__(self, local_states, calculated_actions):
        self.local_states = local_states
        self.calculated_actions = calculated_actions
        self.calculate_inputs = []

    def discover_local_state(self):
        return self.local_states.pop(0)

    def calculate_necessary_state_changes(self, local_state,
                                          desired_configuration,
                                          cluster_state):
        self.calculate_inputs.append(
            (local_state, desired_configuration, cluster_state))
        return self.calculated_actions.pop(0)


class ConvergenceLoopFSMTests(SynchronousTestCase):
    """
    Tests for FSM created by ``build_convergence_loop_fsm``.
    """
    def test_new_stopped(self):
        """
        A newly created FSM is stopped.
        """
        loop = build_convergence_loop_fsm(ControllableDeployer([], []))
        self.assertEqual(loop.state, ConvergenceLoopStates.STOPPED)

    def test_new_status_update_starts_discovery(self):
        """
        A stopped FSM that receives a status update starts discovery.
        """
        deployer = ControllableDeployer([Deferred()], [])
        loop = build_convergence_loop_fsm(deployer)
        loop.receive(_ClientStatusUpdate(client=object(),
                                         configuration=object(),
                                         state=object()))
        self.assertEqual(len(deployer.local_states), 0)  # Discovery started

    def successful_amp_client(self, local_states):
        """
        Create AMP client that can respond successfully to a
        ``NodeStateCommand``.

        :param local_states: The node states we expect to be able to send.

        :return FakeAMPClient: Fake AMP client appropriately setup.
        """
        client = FakeAMPClient()
        for local_state in local_states:
            client.register_response(
                NodeStateCommand, dict(node_state=local_state),
                {"result": None})
        return client

    def test_convergence_done_notify(self):
        """
        A FSM doing convergence that gets a discovery result notifies the last
        received client.
        """
        local_state = object()
        client = self.successful_amp_client([local_state])
        action = ControllableAction(Deferred())
        deployer = ControllableDeployer([succeed(local_state)], [action])
        loop = build_convergence_loop_fsm(deployer)
        loop.receive(_ClientStatusUpdate(client=client,
                                         configuration=object(),
                                         state=object()))
        self.assertEqual(client.calls, [(NodeStateCommand,
                                         dict(node_state=local_state))])

    def test_convergence_done_changes(self):
        """
        A FSM doing convergence that gets a discovery result starts applying
        calculated changes using last received desired configuration and
        cluster state.
        """
        local_state = object()
        configuration = object()
        state = object()
        action = ControllableAction(Deferred())
        deployer = ControllableDeployer([succeed(local_state)], [action])
        loop = build_convergence_loop_fsm(deployer)
        loop.receive(_ClientStatusUpdate(
            client=self.successful_amp_client([local_state]),
            configuration=configuration, state=state))
        # Calculating actions happened, and result was run:
        self.assertEqual((deployer.calculate_inputs, action.called),
                         ([(local_state, configuration, state)], True))

    def test_convergence_done_start_new_iteration(self):
        """
        A FSM doing a convergence iteration does another iteration when
        applying changes is done.
        """
        local_state = object()
        local_state2 = object()
        configuration = object()
        state = object()
        action = ControllableAction(succeed(None))
        action2 = ControllableAction(Deferred())
        deployer = ControllableDeployer(
            [succeed(local_state), succeed(local_state2)],
            [action, action2])
        client = self.successful_amp_client([local_state, local_state2])
        loop = build_convergence_loop_fsm(deployer)
        loop.receive(_ClientStatusUpdate(
            client=client, configuration=configuration, state=state))
        # Calculating actions happened, result was run... and then we did
        # whole thing again:
        self.assertEqual((deployer.calculate_inputs, client.calls),
                         ([(local_state, configuration, state),
                           (local_state2, configuration, state)],
                          [(NodeStateCommand, dict(node_state=local_state)),
                           (NodeStateCommand, dict(node_state=local_state2))]))

    def test_convergence_status_update(self):
        """
        A FSM doing convergence that receives a status update stores the
        client, desired configuration and cluster state, which are then
        used in next convergence iteration.
        """

    def test_convergence_stop(self):
        """
        A FSM doing convergence that receives a stop input stops when the
        convergence iteration finishes.
        """

    def test_convergence_stop_then_status_update(self):
        """
        A FSM doing convergence that receives a stop input and then a status
        update continues on to to next convergence iteration (i.e. stop
        ends up being ignored).
        """
