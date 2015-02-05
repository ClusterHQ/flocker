# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Convergence loop for a node-specific dataset agent.

In practice most of the code is generic, but a few bits assume this agent
is node-specific.

The convergence agent runs a loop that attempts to converge the local
state with the desired configuration as transmitted by the control
service. This involves two state machines: ClusterStatus and ConvergenceLoop.
The ClusterStatus state machine receives inputs from the connection to the
control service, and sends inputs to the ConvergenceLoop state machine.
"""

from characteristic import attributes

from machinist import (
    trivialInput, TransitionTable, constructFiniteStateMachine,
    MethodSuffixOutputer,
    )

from twisted.application.service import Service
from twisted.python.constants import Names, NamedConstant

from ..control._protocol import NodeStateCommand


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
    # Notify the convergence loop state machine of new cluster status:
    UPDATE_STATUS = NamedConstant()
    # Stop the convergence loop state machine:
    STOP = NamedConstant()
    # Disconnect the AMP client:
    DISCONNECT = NamedConstant()


class ClusterStatus(object):
    """
    World object for cluster state machine, executing the actions
    indicated by the outputs.

    :ivar AMP client: The latest AMP protocol instance to connect to the
        control service. Initially ``None``.
    """

    def __init__(self, agent_operation_fsm):
        """
        :param agent_operation_fsm: An convergence loop FSM as output by
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
        self.agent_operation_fsm.receive(ConvergenceLoopInputs.STOP)

    def output_DISCONNECT(self, context):
        self.client.transport.loseConnection()


def build_cluster_status_fsm(convergence_loop_fsm):
    """
    Create a new cluster status FSM.

    :param convergence_loop_fsm: A convergence loop FSM as output by
    ``build_convergence_loop_fsm``.
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
        world=MethodSuffixOutputer(ClusterStatus(convergence_loop_fsm)))


class ConvergenceLoopInputs(Names):
    """
    Inputs for convergence loop FSM.
    """
    # Updated references to latest AMP client, desired configuration and
    # cluster state:
    STATUS_UPDATE = NamedConstant()
    # Stop the convergence loop:
    STOP = NamedConstant()
    # Finished applying necessary changes to local state, a single
    # iteration of the convergence loop:
    ITERATION_DONE = NamedConstant()


@attributes(["client", "configuration", "state"])
class _ClientStatusUpdate(trivialInput(ConvergenceLoopInputs.STATUS_UPDATE)):
    """
    A rich input with a cluster status update - we are currently connected
    to the control service, and know latest desired configuration and
    cluster state.

    :ivar AMP client: An AMP client connected to the control service.
    :ivar Deployment configuration: Desired cluster configuration.
    :ivar Deployment state: Actual cluster state.
    """


class ConvergenceLoopStates(Names):
    """
    Convergence loop FSM states.
    """
    # The loop is stopped:
    STOPPED = NamedConstant()
    # Local state is being discovered and changes applied:
    CONVERGING = NamedConstant()
    # Local state is being converged, and once that is done we will
    # immediately stop:
    CONVERGING_STOPPING = NamedConstant()


class ConvergenceLoopOutputs(Names):
    """
    Converence loop FSM outputs.
    """
    # Store AMP client, desired configuration and cluster state for later
    # use:
    STORE_INFO = NamedConstant()
    # Start an iteration of the covergence loop:
    CONVERGE = NamedConstant()


class ConvergenceLoop(object):
    """
    World object the convergence loop state machine, executing the actions
    indicated by the outputs.

    :ivar AMP client: An AMP client connected to the control
        service. Initially ``None``.

    :ivar Deployment configuration: Desired cluster
        configuration. Initially ``None``.

    :ivar Deployment state: Actual cluster state.  Initially ``None``.

    :ivar fsm: The finite state machine this is part of.
    """
    def __init__(self, deployer):
        """
        :param IDeployer deployer: Used to discover local state and calcualte
            necessary changes to match desired configuration.
        """
        self.deployer = deployer

    def output_STORE_INFO(self, context):
        self.client, self.configuration, self.cluster_state = (
            context.client, context.configuration, context.state)

    def output_CONVERGE(self, context):
        d = self.deployer.discover_local_state()

        def got_local_state(local_state):
            self.client.callRemote(NodeStateCommand, node_state=local_state)
            action = self.deployer.calculate_necessary_state_changes(
                local_state, self.configuration, self.cluster_state)
            action.run(self.deployer)
            #d.addCallback(lambda _: self.fsm.input(ConvergenceLoopInputs.ITERATION_DONE))
        d.addCallback(got_local_state)


def build_convergence_loop_fsm(deployer):
    """
    Create a convergence loop FSM.

    :param IDeployer deployer: Used to discover local state and calcualte
        necessary changes to match desired configuration.
    """
    I = ConvergenceLoopInputs
    O = ConvergenceLoopOutputs
    S = ConvergenceLoopStates

    table = TransitionTable()
    table = table.addTransition(
        S.STOPPED, I.STATUS_UPDATE, [O.STORE_INFO, O.CONVERGE], S.CONVERGING)
    table = table.addTransitions(
        S.CONVERGING, {
            I.STATUS_UPDATE: ([O.STORE_INFO], S.CONVERGING),
            I.STOP: ([], S.CONVERGING_STOPPING),
            I.ITERATION_DONE: ([O.CONVERGE], S.CONVERGING),
        })
    table = table.addTransitions(
        S.CONVERGING_STOPPING, {
            I.STATUS_UPDATE: ([O.STORE_INFO], S.CONVERGING),
            I.ITERATION_DONE: ([], S.STOPPED),
        })

    loop = ConvergenceLoop(deployer)
    fsm = constructFiniteStateMachine(
        inputs=I, outputs=O, states=S, initial=S.STOPPED, table=table,
        richInputs=[_ClientStatusUpdate], inputContext={},
        world=MethodSuffixOutputer(loop))
    loop.fsm = fsm
    return fsm


class AgentLoopService(Service):

    def __init__(self, deployment, host, port):
        self.convergence_loop = build_convergence_loop_fsm(deployment)
        self.cluster_status = build_cluster_status_fsm(self.convergence_loop)

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
        # input _ClientConnected to self.convergence_loop, pass reference to client in
        pass

    def disconnected(self):
        # input DISCONNECTED to self.cluster_status
        pass

    def cluster_updated(configuration, cluster_state):
        # input _StatusUpdate with config and state to self.cluster_status
        pass
