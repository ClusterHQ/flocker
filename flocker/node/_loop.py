"""
Convergence loop for a node-specific dataset agent.

In practice most of the code is generic, but a few bits assume this agent
is node-specific.

The convergence agent runs a loop that attempts to converge the local
state with the desired configuration as transmitted by the control
service. This involves two state machines: ClusterStatus and AgentOperation.
The ClusterStatus state machine receives inputs from the connection to the
control service, and sends inputs to the AgentOperation state machine.

What's below isn't quite accurate anymore; the prose will be turned into
comments on the state machine setup as part of coding.

ClusterStatus has the following states:

DISCONNECTED:

The agent is not connected to the control service.
If connected switch to IGNORANT.
If connection failed try to connect again.

IGNORANT:

The status of the cluster is unknown.
If desired configuration and cluster state are received send a GO input
symbol to the AgentOperation state machine. switch to KNOWLEDGEABLE.
If disconnected then switch to DISCONNECTED.

KNOWLEDGEABLE:

The status of the cluster is known.
If disconnected send a STOP input to AgentOperation and switch to DISCONNECTED.


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

from machinist import (
    trivialInput, TransitionTable, constructFiniteStateMachine,
    MethodSuffixOutputer,
    )

from twisted.python.constants import Names, NamedConstant


class ClusterStatusInputs(Names):
    CLIENT_CONNECTED = NamedConstant()
    STATUS_UPDATE = NamedConstant()
    CLIENT_DISCONNECTED = NamedConstant()
    SHUTDOWN = NamedConstant()


class _ClientConnected(trivialInput(ClusterStatusInputs.CLIENT_CONNECTED)):
    def __init__(self, client):
        """
        :param AMP client: An AMP client connected to the control service.
        """
        self.client = client


class _StatusUpdate(trivialInput(ClusterStatusInputs.STATUS_UPDATE)):
    def __init__(self, configuration, state):
        """
        :param Deployment configuration: Desired cluster configuration.
        :param Deployment state: Actual cluster state.
        """
        self.configuration = configuration
        self.state = state


class ClusterStatusStates(Names):
    DISCONNECTED = NamedConstant()
    IGNORANT = NamedConstant()
    KNOWLEDGEABLE = NamedConstant()
    SHUTDOWN = NamedConstant()


class ClusterStatusOutputs(Names):
    STORE_CLIENT = NamedConstant()
    READY = NamedConstant()
    NOT_READY = NamedConstant()
    DISCONNECT = NamedConstant()


class ClusterStatus(object):
    def __init__(self, agent_operation_fsm):
        self.agent_operation_fsm = agent_operation_fsm

    def output_STORE_CLIENT(self, symbol, context):
        self.client = context.client

    def output_READY(self, symbol, context):
        self.agent_operation_fsm.input(
            _Go(self.client, context.configuration, context.state))

    def output_NOT_READY(self, symbol, context):
        self.agent_operation_fsm.input(AgentOperationInputs.STOP)

    def output_DISCONNECT(self, symbol, context):
        self.client.transport.abortConnection()


def build_cluster_status_fsm(agent_operation_fsm):
    S = ClusterStatusStates
    I = ClusterStatusInputs
    O = ClusterStatusOutputs
    table = TransitionTable()
    table = table.addTransitions(
        S.DISCONNECTED, {
            I.CLIENT_CONNECTED: ([O.STORE_CLIENT], S.IGNORANT),
            I.SHUTDOWN: ([], S.SHUTDOWN),
        })
    table = table.addTransitions(
        S.IGNORANT, {
            I.CLIENT_DISCONNECTED: ([], S.DISCONNECTED),
            I.STATUS_UPDATE: ([O.READY], S.KNOWLEDGEABLE),
            I.SHUTDOWN: ([O.DISCONNECT], S.SHUTDOWN),
        })
    table = table.addTransitions(
        S.KNOWLEDGEABLE, {
            I.STATUS_UPDATE: ([], S.KNOWLEDGEABLE),
            I.CLIENT_DISCONNECTED: ([O.NOT_READY], S.DISCONNECTED),
            I.SHUTDOWN: ([O.NOT_READY, O.DISCONNECT], S.SHUTDOWN),
        })

    return constructFiniteStateMachine(
        inputs=I, outputs=O, states=S, table=table,
        richInput=[_ClientConnected, _StatusUpdate],
        inputContext={}, world=MethodSuffixOutputer(
            ClusterStatus(agent_operation_fsm)))


class AgentOperationInputs(Names):
    GO = NamedConstant()
    STOP = NamedConstant()
    DISCOVERED_STATUS = NamedConstant()
    CHANGES_DONE = NamedConstant()


class _Go(trivialInput(AgentOperationInputs.GO)):
    def __init__(self, client, configuration, state):
        pass


class _DiscoveredStatus(trivialInput(AgentOperationInputs.DiSCOVERED_STATUS)): 
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

    def output_STORE_INFO(self, symbol, context):
        self.client, self.configuration, self.cluster_state = (
            context.client, context.configuration, context.state)

    def output_DISCOVER(self, symbol, context):
        d = self.deployer.discover_node_configuration()
        d.addCallback(
            lambda node_state: self.input(_DiscoveredStatus(node_state)))
        # XXX error case

    def output_REPORT_NODE_STATE(self, symbol, context):
        self.client.callRemote(NodeStateCommand, node_state=context.node_state)

    def output_CHANGE(self, symbol, context):
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
            AgentOperation(deployer))


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
