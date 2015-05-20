# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for ``flocker.node._loop``.
"""

from uuid import uuid4

from eliot.testing import validate_logging, assertHasAction, assertHasMessage
from machinist import LOG_FSM_TRANSITION

from twisted.trial.unittest import SynchronousTestCase
from twisted.test.proto_helpers import StringTransport, MemoryReactorClock
from twisted.internet.protocol import Protocol, ReconnectingClientFactory
from twisted.internet.defer import succeed, Deferred, fail
from twisted.internet.task import Clock
from twisted.internet.ssl import ClientContextFactory
from twisted.protocols.tls import TLSMemoryBIOFactory, TLSMemoryBIOProtocol

from ...testtools import FakeAMPClient
from .._loop import (
    build_cluster_status_fsm, ClusterStatusInputs, _ClientStatusUpdate,
    _StatusUpdate, _ConnectedToControlService, ConvergenceLoopInputs,
    ConvergenceLoopStates, build_convergence_loop_fsm, AgentLoopService,
    LOG_SEND_TO_CONTROL_SERVICE,
    LOG_CONVERGE, LOG_CALCULATED_ACTIONS,
    )
from ..testtools import ControllableDeployer, ControllableAction, to_node
from ...control import (
    NodeState, Deployment, Manifestation, Dataset, DeploymentState,
)
from ...control._protocol import NodeStateCommand, AgentAMP
from ...control.test.test_protocol import iconvergence_agent_tests_factory


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
        client = build_protocol()
        self.fsm.receive(_ConnectedToControlService(client=client))
        self.fsm.receive(_StatusUpdate(configuration=object(),
                                       state=object()))
        self.assertFalse(client.transport.disconnecting)

    def test_disconnect_before_status_update(self):
        """
        If the client disconnects before a status update is received then no
        notification is needed for convergence loop FSM.
        """
        self.fsm.receive(_ConnectedToControlService(client=build_protocol()))
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
        client = build_protocol()
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
        client = build_protocol()
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
        client = build_protocol()
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
        client = build_protocol()
        desired = object()
        state = object()
        self.fsm.receive(_ConnectedToControlService(client=client))
        self.fsm.receive(ClusterStatusInputs.SHUTDOWN)
        self.fsm.receive(_StatusUpdate(configuration=desired, state=state))
        # We never send anything to convergence loop FSM:
        self.assertConvergenceLoopInputted([])


class ConvergenceLoopFSMTests(SynchronousTestCase):
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
                NodeStateCommand, dict(state_changes=(local_state,)),
                {"result": None})
        return client

    @validate_logging(assertHasAction, LOG_SEND_TO_CONTROL_SERVICE, True)
    def test_convergence_done_notify(self, logger):
        """
        A FSM doing convergence that gets a discovery result, sends the
        discovered state to the control service using the last received
        client.
        """
        local_state = NodeState(hostname=u"192.0.2.123")
        client = self.successful_amp_client([local_state])
        action = ControllableAction(result=Deferred())
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
        client = self.successful_amp_client([local_node_state])
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

        (actual_local_state,
         actual_desired_configuration,
         actual_cluster_state) = calculate_necessary_state_changes_inputs

        self.assertEqual(expected_local_cluster_state, actual_cluster_state)

    def test_convergence_done_changes(self):
        """
        A FSM doing convergence that gets a discovery result starts applying
        calculated changes using last received desired configuration and
        cluster state.
        """
        local_state = NodeState(hostname=u'192.0.2.123')
        configuration = object()
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
            client=self.successful_amp_client([local_state]),
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
    def test_convergence_done_delays_new_iteration(self, logger):
        """
        An FSM completing the changes from one convergence iteration doesn't
        instantly start another iteration.
        """
        self.local_state = local_state = NodeState(hostname=u'192.0.2.123')
        self.configuration = configuration = Deployment()
        self.cluster_state = received_state = DeploymentState(nodes=[])
        self.action = action = ControllableAction(result=succeed(None))
        deployer = ControllableDeployer(
            local_state.hostname, [succeed(local_state)], [action]
        )
        client = self.successful_amp_client([local_state])
        reactor = Clock()
        loop = build_convergence_loop_fsm(reactor, deployer)
        self.patch(loop, "logger", logger)
        loop.receive(_ClientStatusUpdate(
            client=client, configuration=configuration, state=received_state))

        expected_cluster_state = DeploymentState(
            nodes=[local_state])

        # Calculating actions happened and the result was run.
        self.assertTupleEqual(
            (deployer.calculate_inputs, client.calls),
            ([(local_state, configuration, expected_cluster_state)],
             [(NodeStateCommand, dict(state_changes=(local_state,)))])
        )

    def test_convergence_done_start_new_iteration(self):
        """
        After a short delay, an FSM completing the changes from one convergence
        iteration starts another iteration.
        """
        local_state = NodeState(hostname=u'192.0.2.123')
        local_state2 = NodeState(hostname=u'192.0.2.123')
        configuration = Deployment(nodes=frozenset([to_node(local_state)]))
        state = DeploymentState(nodes=[local_state])
        action = ControllableAction(result=succeed(None))
        # Because the second action result is unfired Deferred, the second
        # iteration will never finish; applying its changes waits for this
        # Deferred to fire.
        action2 = ControllableAction(result=Deferred())
        deployer = ControllableDeployer(
            local_state.hostname,
            [succeed(local_state), succeed(local_state2)],
            [action, action2])
        client = self.successful_amp_client([local_state, local_state2])
        reactor = Clock()
        loop = build_convergence_loop_fsm(reactor, deployer)
        loop.receive(_ClientStatusUpdate(
            client=client, configuration=configuration, state=state))
        reactor.advance(1.0)
        # Calculating actions happened, result was run... and then we did
        # whole thing again:
        self.assertTupleEqual(
            (deployer.calculate_inputs, client.calls),
            ([(local_state, configuration, state),
              (local_state2, configuration, state)],
             [(NodeStateCommand, dict(state_changes=(local_state,))),
              (NodeStateCommand, dict(state_changes=(local_state2,)))])
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
        action = ControllableAction(result=fail(RuntimeError()))
        # First discovery succeeds, leading to failing action; second
        # discovery will just wait for Deferred to fire. Thus we expect to
        # finish test in discovery state.
        deployer = ControllableDeployer(
            local_state.hostname,
            [succeed(local_state), Deferred()],
            [action])
        client = self.successful_amp_client([local_state])
        reactor = Clock()
        loop = build_convergence_loop_fsm(reactor, deployer)
        self.patch(loop, "logger", logger)
        loop.receive(_ClientStatusUpdate(
            client=client, configuration=configuration, state=state))
        reactor.advance(1.0)
        # Calculating actions happened, result was run and caused error...
        # but we started on loop again and are thus in discovery state,
        # which we can tell because all faked local states have been
        # consumed:
        self.assertEqual(len(deployer.local_states), 0)

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
        client = self.successful_amp_client([local_state])
        reactor = Clock()
        loop = build_convergence_loop_fsm(reactor, deployer)
        loop.receive(_ClientStatusUpdate(
            client=client, configuration=configuration, state=state))

        # Calculating actions happened, action is run, but waits for
        # Deferred to be fired... Meanwhile a new status update appears!
        client2 = self.successful_amp_client([local_state2])
        configuration2 = Deployment(nodes=frozenset([to_node(local_state)]))
        state2 = DeploymentState(nodes=[local_state])
        loop.receive(_ClientStatusUpdate(
            client=client2, configuration=configuration2, state=state2))
        # Action finally finishes, and we can move on to next iteration,
        # which happens with second set of client, desired configuration
        # and cluster state:
        action.result.callback(None)
        reactor.advance(1.0)

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
        client = self.successful_amp_client([local_state])
        reactor = Clock()
        loop = build_convergence_loop_fsm(reactor, deployer)
        loop.receive(_ClientStatusUpdate(
            client=client, configuration=configuration, state=state))

        # Calculating actions happened, action is run, but waits for
        # Deferred to be fired... Meanwhile a stop input is received!
        loop.receive(ConvergenceLoopInputs.STOP)
        # Action finally finishes:
        action.result.callback(None)
        reactor.advance(1.0)

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
        update continues on to to next convergence iteration (i.e. stop
        ends up being ignored).
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
        client = self.successful_amp_client([local_state])
        reactor = Clock()
        loop = build_convergence_loop_fsm(reactor, deployer)
        loop.receive(_ClientStatusUpdate(
            client=client, configuration=configuration, state=state))

        # Calculating actions happened, action is run, but waits for
        # Deferred to be fired... Meanwhile a new status update appears!
        client2 = self.successful_amp_client([local_state2])
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
        reactor.advance(1.0)
        self.assertTupleEqual(
            (deployer.calculate_inputs, client.calls, client2.calls),
            ([(local_state, configuration, state),
              (local_state2, configuration2, state2)],
             [(NodeStateCommand, dict(state_changes=(local_state,)))],
             [(NodeStateCommand, dict(state_changes=(local_state2,)))]))


class AgentLoopServiceTests(SynchronousTestCase):
    """
    Tests for ``AgentLoopService``.
    """
    def setUp(self):
        self.deployer = ControllableDeployer(u"127.0.0.1", [], [])
        self.reactor = MemoryReactorClock()
        self.service = AgentLoopService(
            reactor=self.reactor, deployer=self.deployer, host=u"example.com",
            port=1234, context_factory=ClientContextFactory())

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
        client = object()
        service.connected(client)
        self.assertEqual(fsm.inputted,
                         [_ConnectedToControlService(client=client)])

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
        config = object()
        state = object()
        service.cluster_updated(config, state)
        self.assertEqual(fsm.inputted, [_StatusUpdate(configuration=config,
                                                      state=state)])


def _build_service(test):
    """
    Fixture for creating ``AgentLoopService``.
    """
    service = AgentLoopService(
        reactor=None, deployer=object(), host=u"example.com", port=1234,
        context_factory=ClientContextFactory())
    service.cluster_status = StubFSM()
    return service


class AgentLoopServiceInterfaceTests(
        iconvergence_agent_tests_factory(_build_service)):
    """
    ``IConvergenceAgent`` tests for ``AgentLoopService``.
    """
