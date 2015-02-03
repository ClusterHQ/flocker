# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Convergence loop for a node-specific dataset agent.

In practice most of the code is generic, but a few bits assume this agent
is node-specific.

The convergence agent runs a loop that attempts to converge the local
state with the desired configuration as transmitted by the control
service. This involves two state machines: ClusterStatus and AgentOperation.
The ClusterStatus state machine receives inputs from the connection to the
control service, and sends inputs to the AgentOperation state machine.


AgentOperation has the following states:

STOPPED:

Nothing going on.
When GO is received start discovery and switch to DISCOVERING.

DISCOVERING:

Discovery is ongoing.
When discovery result is received send it (asynchronously) to control
service, start changing local state appropriately, switch to CHANGING.
If STOP is received switch to DISCOVERING_STOPPING.

DISCOVERING_STOPPING:

If discovery result is received switch to STOPPED.
If GO is received switch to DISCOVERING.

CHANGING:

Change is ongoing.
If changes finish start discovery and switch to DISCOVERING.
If STOP is received switch to CHANGING_STOPPING.

CHANGING_STOPPING:

If changes finish switch to STOPPED.
If GO is received switch to CHANGING.
"""

from characteristic import attributes

from machinist import (
    trivialInput, TransitionTable, constructFiniteStateMachine,
    MethodSuffixOutputer,
    )

from twisted.application.service import Service
from twisted.python.constants import Names, NamedConstant


class ClusterStatusInputs(Names):
    """
    Inputs to the cluster status state machine.
    """
    # The client has connected to the control service:
    CLIENT_CONNECTED = NamedConstant()
    # A status update has been received from the control service:
    STATUS_UPDATE = NamedConstant()
    # THe client has disconnected from the control service:
    CLIENT_DISCONNECTED = NamedConstant()
    # The system is shutting down:
    SHUTDOWN = NamedConstant()


@attributes(["client"])
class _ClientConnected(trivialInput(ClusterStatusInputs.CLIENT_CONNECTED)):
    """
    A rich input indicating the client has connected.

    :ivar AMP client: An AMP client connected to the control service.
    """


@attributes(["configuration", "state"])
class _StatusUpdate(trivialInput(ClusterStatusInputs.STATUS_UPDATE)):
    """
    A rich input indicating the cluster status has been received from the
    control service.

    :ivar Deployment configuration: Desired cluster configuration.
    :ivar Deployment state: Actual cluster state.
    """


class ClusterStatusStates(Names):
    """
    States of the cluster status state machine.
    """
    # The client is currently disconnected:
    DISCONNECTED = NamedConstant()
    # The client is connected, we don't know cluster status:
    IGNORANT = NamedConstant()
    # The client is connected and we know the cluster status:
    KNOWLEDGEABLE = NamedConstant()
    # The system is shut down:
    SHUTDOWN = NamedConstant()


class ClusterStatusOutputs(Names):
    """
    Outputs of the cluster status state machine.
    """
    # Store the AMP protocol instance connected to the server:
    STORE_CLIENT = NamedConstant()
    # Notify the agent operation state machine of new cluster status:
    UPDATE_STATUS = NamedConstant()
    # Stop the agent operation state machine:
    STOP = NamedConstant()
    # Disconnect the AMP client:
    DISCONNECT = NamedConstant()


class ClusterStatus(object):
    """
    World object for cluster status machine, executing the actions
    indicated by the outputs.

    :ivar AMP client: The latest AMP protocol instance to connect to the
        control service. Initially ``None``.
    """

    def __init__(self, agent_operation_fsm):
        """
        :param agent_operation_fsm: An agent operation FSM as output by
            ``build_agent_operation_fsm``.
        """
        self.agent_operation_fsm = agent_operation_fsm
        self.client = None

    def output_STORE_CLIENT(self, context):
        self.client = context.client

    def output_UPDATE_STATUS(self, context):
        self.agent_operation_fsm.receive(
            _ClientStatusUpdate(client=self.client,
                                configuration=context.configuration,
                                state=context.state))

    def output_STOP(self, context):
        self.agent_operation_fsm.receive(AgentOperationInputs.STOP)

    def output_DISCONNECT(self, context):
        self.client.transport.loseConnection()


def build_cluster_status_fsm(agent_operation_fsm):
    """
    Create a new cluster status FSM.

    :param agent_operation_fsm: An agent operation FSM as output by
    ``build_agent_operation_fsm``.
    """
    S = ClusterStatusStates
    I = ClusterStatusInputs
    O = ClusterStatusOutputs
    table = TransitionTable()
    # We may be shut down in any state, in which case we disconnect if
    # necessary.
    table = table.addTransitions(
        S.DISCONNECTED, {
            # Store the client, then wait for cluster status to be sent
            # over AMP:
            I.CLIENT_CONNECTED: ([O.STORE_CLIENT], S.IGNORANT),
            I.SHUTDOWN: ([], S.SHUTDOWN),
        })
    table = table.addTransitions(
        S.IGNORANT, {
            # We never told agent to start, so no need to tell it to stop:
            I.CLIENT_DISCONNECTED: ([], S.DISCONNECTED),
            # Tell agent latest cluster status, implicitly starting it:
            I.STATUS_UPDATE: ([O.UPDATE_STATUS], S.KNOWLEDGEABLE),
            I.SHUTDOWN: ([O.DISCONNECT], S.SHUTDOWN),
        })
    table = table.addTransitions(
        S.KNOWLEDGEABLE, {
            # Tell agent latest cluster status:
            I.STATUS_UPDATE: ([O.UPDATE_STATUS], S.KNOWLEDGEABLE),
            I.CLIENT_DISCONNECTED: ([O.STOP], S.DISCONNECTED),
            I.SHUTDOWN: ([O.STOP, O.DISCONNECT], S.SHUTDOWN),
        })
    table = table.addTransitions(
        S.SHUTDOWN, {
            I.CLIENT_DISCONNECTED: ([], S.SHUTDOWN),
            I.STATUS_UPDATE: ([], S.SHUTDOWN),
            })

    return constructFiniteStateMachine(
        inputs=I, outputs=O, states=S, initial=S.DISCONNECTED, table=table,
        richInputs=[_ClientConnected, _StatusUpdate], inputContext={},
        world=MethodSuffixOutputer(ClusterStatus(agent_operation_fsm)))


class AgentOperationInputs(Names):
    STATUS_UPDATE = NamedConstant()
    STOP = NamedConstant()
    DISCOVERED_STATUS = NamedConstant()
    CHANGES_DONE = NamedConstant()


@attributes(["client", "configuration", "state"])
class _ClientStatusUpdate(trivialInput(AgentOperationInputs.STATUS_UPDATE)):
    pass


class _DiscoveredStatus(trivialInput(AgentOperationInputs.DISCOVERED_STATUS)):
    def __init__(self, node_state):
        pass


class AgentOperationStates(Names):
    STOPPED = NamedConstant()
    DISCOVERING = NamedConstant()
    DISCOVERING_STOPPING = NamedConstant()
    CHANGING = NamedConstant()
    CHANGING_STOPPING = NamedConstant()


class AgentOperationOutputs(Names):
    STORE_INFO = NamedConstant()
    DISCOVER = NamedConstant()
    REPORT_NODE_STATE = NamedConstant()
    CHANGE = NamedConstant()


class AgentOperation(object):
    def __init__(self, deployer):
        self.deployer = deployer

    def output_STORE_INFO(self, context):
        self.client, self.configuration, self.cluster_state = (
            context.client, context.configuration, context.state)

    def output_DISCOVER(self, context):
        d = self.deployer.discover_node_configuration()
        d.addCallback(
            lambda node_state: self.input(_DiscoveredStatus(node_state)))
        # XXX error case

    def output_REPORT_NODE_STATE(self, context):
        self.client.callRemote(NodeStateCommand, node_state=context.node_state)

    def output_CHANGE(self, context):
        # XXX need to refactor Deployer slightly so you can pass in NodeState...
        d = self.deployer.change_node_state(self.configuration, self.cluster_state,
                                            HOSTNAME)
        d.addCallback(lambda _: self.input(AgentOperationInputs.CHANGES_DONE))
        # XXX log error and do same input anyway


def build_agent_operation_fsm(deployer):
    I = AgentOperationInputs
    O = AgentOperationOutputs
    S = AgentOperationStates

    table = TransitionTable()
    table = table.addTransition(
        S.STOPPED, I.GO, [O.STORE_INFO, O.DISCOVER], S.DISCOVERING)
    table = table.addTransitions(
        S.DISCOVERING, {
            I.STOP: ([], S.DISCOVERING_STOPPING),
            I.DISCOVERED_STATUS: ([O.REPORT_NODE_STATE, O.CHANGE], S.CHANGING),
        })
    table = table.addTransitions(
        S.DISCOVERING_STOPPING, {
            I.GO: ([O.STORE_INFO], S.DISCOVERING),
            I.DISCOVERED_STATUS: ([], S.STOPPED),
        })
    table = table.addTransitions(
        S.CHANGING, {
            I.STOP: ([], S.CHANGING_STOPPING),
            I.CHANGES_DONE: ([O.DISCOVER], S.DISCOVERING),
            })
    table = table.addTransitions(
        S.CHANGING_STOPPING, {
            I.GO: ([], S.CHANGING),
            I.CHANGES_DONE: ([], S.STOPPED),
            })
    return constructFiniteStateMachine(
        inputs=I, outputs=O, states=S, table=table,
        richInput=[_Go, _DiscoveredStatus],
        inputContext={}, world=MethodSuffixOutputer(
            AgentOperation(deployer)))


class AgentLoopService(Service):

    def __init__(self, deployment, host, port):
        self.agent_operation = build_agent_operation_fsm(deployment)
        self.cluster_status = build_cluster_status_fsm(self.agent_operation)

    def startService(self):
        self.factory = ReconnectingClientFactory()
        self.factory.protocol = lambda: AgentClient(self)
        reactor.connectTCP(self.host, self.port)

    def stopService(self):
        # stop factory
        # input SHUTDOWN to self.cluster_status
        # return Defererd that fires when everything has been closed
        pass

    def connected(self, client):
        # input _ClientConnected to self.agent_operation, pass reference to client in
        pass

    def disconnected(self):
        # input DISCONNECTED to self.cluster_status
        pass

    def cluster_updated(configuration, cluster_state):
        # input _StatusUpdate with config and state to self.cluster_status
        pass
