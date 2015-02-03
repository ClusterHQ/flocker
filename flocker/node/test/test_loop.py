# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for ``flocker.node._loop``.
"""

from twisted.trial.unittest import SynchronousTestCase
from twisted.test.proto_helpers import StringTransport
from twisted.internet.protocol import Protocol

from .._loop import (
    build_cluster_status_fsm, ClusterStatusInputs, _ClientStatusUpdate,
    _StatusUpdate, _ClientConnected, AgentOperationInputs
    )


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

    def assertAgentOperationInputted(self, expected):
        """
        Assert that that given set of symbols were input to the agent
        operation FSM.
        """
        self.assertEqual(self.agent_operation.inputted, expected)

    def test_creation_no_side_effects(self):
        """
        Creating the FSM has no side effects.
        """
        self.assertAgentOperationInputted([])

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
        self.assertAgentOperationInputted(
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
        self.assertAgentOperationInputted(
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
        self.assertAgentOperationInputted([])

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
        self.assertAgentOperationInputted(
            [_ClientStatusUpdate(client=client, configuration=desired,
                                 state=state),
             AgentOperationInputs.STOP])

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
        self.assertAgentOperationInputted(
            [_ClientStatusUpdate(client=client, configuration=desired,
                                 state=state),
             AgentOperationInputs.STOP,
             _ClientStatusUpdate(client=client2, configuration=desired2,
                                 state=state2)])

    def test_shutdown_before_connect(self):
        """
        If the FSM is shutdown before a connection is made nothing happens.
        """
        self.fsm.receive(ClusterStatusInputs.SHUTDOWN)
        self.assertAgentOperationInputted([])

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
                         (True, AgentOperationInputs.STOP))

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
        self.assertAgentOperationInputted([
            _ClientStatusUpdate(client=client, configuration=desired,
                                state=state),
            # This is caused by the shutdown... and the disconnect results
            # in no further messages:
            AgentOperationInputs.STOP])

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
        self.assertAgentOperationInputted([])


class AgentOperationFSMTests(SynchronousTestCase):
    """
    Tests for FSM created by ``build_agent_operation_fsm``.
    """
