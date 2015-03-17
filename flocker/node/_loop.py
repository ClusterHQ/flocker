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

from zope.interface import implementer

from characteristic import attributes

from machinist import (
    trivialInput, TransitionTable, constructFiniteStateMachine,
    MethodSuffixOutputer,
    )

from twisted.application.service import MultiService
from twisted.python.constants import Names, NamedConstant
from twisted.internet.protocol import ReconnectingClientFactory

from ..control._protocol import (
    NodeStateCommand, IConvergenceAgent, AgentAMP,
    )


class ClusterStatusInputs(Names):
    """
    Inputs to the cluster status state machine.
    """
    # The client has connected to the control service:
    CONNECTED_TO_CONTROL_SERVICE = NamedConstant()
    # A status update has been received from the control service:
    STATUS_UPDATE = NamedConstant()
    # THe client has disconnected from the control service:
    DISCONNECTED_FROM_CONTROL_SERVICE = NamedConstant()
    # The system is shutting down:
    SHUTDOWN = NamedConstant()


@attributes(["client"])
class _ConnectedToControlService(
        trivialInput(ClusterStatusInputs.CONNECTED_TO_CONTROL_SERVICE)):
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

    def __init__(self, convergence_loop_fsm):
        """
        :param convergence_loop_fsm: An convergence loop FSM as output by
            ``build_convergence_loop_fsm``.
        """
        self.convergence_loop_fsm = convergence_loop_fsm
        self.client = None

    def output_STORE_CLIENT(self, context):
        self.client = context.client

    def output_UPDATE_STATUS(self, context):
        self.convergence_loop_fsm.receive(
            _ClientStatusUpdate(client=self.client,
                                configuration=context.configuration,
                                state=context.state))

    def output_STOP(self, context):
        self.convergence_loop_fsm.receive(ConvergenceLoopInputs.STOP)

    def output_DISCONNECT(self, context):
        self.client.transport.loseConnection()
        self.client = None


def build_cluster_status_fsm(convergence_loop_fsm):
    """
    Create a new cluster status FSM.

    The automatic reconnection logic is handled by the
    ``AgentLoopService``; the world object here just gets notified of
    disconnects, it need schedule the reconnect itself.

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
            I.CONNECTED_TO_CONTROL_SERVICE: ([O.STORE_CLIENT], S.IGNORANT),
            I.SHUTDOWN: ([], S.SHUTDOWN),
        })
    table = table.addTransitions(
        S.IGNORANT, {
            # We never told agent to start, so no need to tell it to stop:
            I.DISCONNECTED_FROM_CONTROL_SERVICE: ([], S.DISCONNECTED),
            # Tell agent latest cluster status, implicitly starting it:
            I.STATUS_UPDATE: ([O.UPDATE_STATUS], S.KNOWLEDGEABLE),
            I.SHUTDOWN: ([O.DISCONNECT], S.SHUTDOWN),
        })
    table = table.addTransitions(
        S.KNOWLEDGEABLE, {
            # Tell agent latest cluster status:
            I.STATUS_UPDATE: ([O.UPDATE_STATUS], S.KNOWLEDGEABLE),
            I.DISCONNECTED_FROM_CONTROL_SERVICE: ([O.STOP], S.DISCONNECTED),
            I.SHUTDOWN: ([O.STOP, O.DISCONNECT], S.SHUTDOWN),
        })
    table = table.addTransitions(
        S.SHUTDOWN, {
            I.DISCONNECTED_FROM_CONTROL_SERVICE: ([], S.SHUTDOWN),
            I.STATUS_UPDATE: ([], S.SHUTDOWN),
            })

    return constructFiniteStateMachine(
        inputs=I, outputs=O, states=S, initial=S.DISCONNECTED, table=table,
        richInputs=[_ConnectedToControlService, _StatusUpdate],
        inputContext={},
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
    World object for the convergence loop state machine, executing the actions
    indicated by the outputs from the state machine.

    :ivar AMP client: An AMP client connected to the control
        service. Initially ``None``.

    :ivar Deployment configuration: Desired cluster
        configuration. Initially ``None``.

    :ivar Deployment state: Actual cluster state.  Initially ``None``.

    :ivar fsm: The finite state machine this is part of.
    """
    def __init__(self, reactor, deployer):
        """
        :param IReactorTime reactor: Used to schedule delays in the loop.

        :param IDeployer deployer: Used to discover local state and calculate
            necessary changes to match desired configuration.
        """
        self.reactor = reactor
        self.deployer = deployer

    def output_STORE_INFO(self, context):
        self.client, self.configuration, self.cluster_state = (
            context.client, context.configuration, context.state)

    def output_CONVERGE(self, context):
        d = self.deployer.discover_local_state()

        def got_local_state(local_state):
            # Current cluster state is likely out of date as regards the local
            # state, so update it accordingly:
            self.cluster_state = self.cluster_state.update_node(
                local_state.to_node()
            )
            self.client.callRemote(NodeStateCommand, node_state=local_state)
            action = self.deployer.calculate_necessary_state_changes(
                local_state, self.configuration, self.cluster_state
            )
            return action.run(self.deployer)
        d.addCallback(got_local_state)

        # It would be better to have a "quiet time" state in the FSM and
        # transition to that next, then have a timeout input kick the machine
        # back around to the beginning of the loop in the FSM.  However, we're
        # not going to keep this sleep-for-a-bit solution in the long term.
        # Instead, we'll be more event driven.  So just going with the simple
        # solution and inserting a side-effect-y delay directly here.

        d.addCallback(
            lambda _:
                self.reactor.callLater(
                    1.0, self.fsm.receive, ConvergenceLoopInputs.ITERATION_DONE
                )
        )
        # This needs error handling:
        # https://clusterhq.atlassian.net/browse/FLOC-1357


def build_convergence_loop_fsm(reactor, deployer):
    """
    Create a convergence loop FSM.

    :param IReactorTime reactor: Used to schedule delays in the loop.

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

    loop = ConvergenceLoop(reactor, deployer)
    fsm = constructFiniteStateMachine(
        inputs=I, outputs=O, states=S, initial=S.STOPPED, table=table,
        richInputs=[_ClientStatusUpdate], inputContext={},
        world=MethodSuffixOutputer(loop))
    loop.fsm = fsm
    return fsm


@implementer(IConvergenceAgent)
@attributes(["reactor", "deployer", "host", "port"])
class AgentLoopService(object, MultiService):
    """
    Service in charge of running the convergence loop.

    :ivar reactor: The reactor.
    :ivar IDeployer deployer: Deployer for discovering local state and
            then changing it.
    :ivar host: Host to connect to.
    :ivar port: Port to connect to.
    :ivar cluster_status: A cluster status FSM.
    :ivar factory: The factory used to connect to the control service.
    """

    def __init__(self):
        MultiService.__init__(self)
        convergence_loop = build_convergence_loop_fsm(
            self.reactor, self.deployer
        )
        self.cluster_status = build_cluster_status_fsm(convergence_loop)
        self.factory = ReconnectingClientFactory.forProtocol(
            lambda: AgentAMP(self))

    def startService(self):
        MultiService.startService(self)
        self.reactor.connectTCP(self.host, self.port, self.factory)

    def stopService(self):
        MultiService.stopService(self)
        self.factory.stopTrying()
        self.cluster_status.receive(ClusterStatusInputs.SHUTDOWN)

    # IConvergenceAgent methods:

    def connected(self, client):
        self.cluster_status.receive(_ConnectedToControlService(client=client))

    def disconnected(self):
        self.cluster_status.receive(
            ClusterStatusInputs.DISCONNECTED_FROM_CONTROL_SERVICE)

    def cluster_updated(self, configuration, cluster_state):
        self.cluster_status.receive(_StatusUpdate(configuration=configuration,
                                                  state=cluster_state))
