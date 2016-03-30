# Copyright ClusterHQ Inc.  See LICENSE file for details.
# -*- test-case-name: flocker.node.test.test_loop -*-

"""
Convergence loop for a node-specific dataset agent.

In practice most of the code is generic, but a few bits assume this agent
is node-specific.

The convergence agent runs a loop that attempts to converge the local
state with the desired configuration as transmitted by the control
service. This involves two state machines: ClusterStatus and ConvergenceLoop.
The ClusterStatus state machine receives inputs from the connection to the
control service, and sends inputs to the ConvergenceLoop state machine.

:var TransitionTable _CLUSTER_STATUS_FSM_TABLE: See
    ``_build_cluster_status_fsm_table``.
:var TransitionTable _CONVERGENCE_LOOP_FSM_TABLE: See
    ``_build_cluster_status_fsm_table``.
"""

from random import uniform

from zope.interface import implementer

from eliot import (
    ActionType, Field, writeFailure, MessageType, write_traceback, Message
)
from eliot.twisted import DeferredContext

from pyrsistent import field, PClass

from characteristic import attributes

from machinist import (
    trivialInput, TransitionTable, constructFiniteStateMachine,
    MethodSuffixOutputer,
)

from twisted.application.service import MultiService
from twisted.python.constants import Names, NamedConstant
from twisted.internet.defer import succeed, maybeDeferred
from twisted.internet.protocol import ReconnectingClientFactory
from twisted.protocols.tls import TLSMemoryBIOFactory
from twisted.python.reflect import safe_repr

from . import run_state_change, NoOp

from ..common import gather_deferreds
from ..control import (
    NodeStateCommand, IConvergenceAgent, AgentAMP, SetNodeEraCommand,
    IStatePersister, SetBlockDeviceIdForDatasetId,
)
from ..control._persistence import to_unserialized_json


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


def _build_cluster_status_fsm_table():
    """
    Create the ``TransitionTable`` needed by the cluster status FSM.

    :return TransitionTable: The transition table for the state machine for
        keeping track of cluster state and configuration.
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
    return table


_CLUSTER_STATUS_FSM_TABLE = _build_cluster_status_fsm_table()


def build_cluster_status_fsm(convergence_loop_fsm):
    """
    Create a new cluster status FSM.

    The automatic reconnection logic is handled by the
    ``AgentLoopService``; the world object here just gets notified of
    disconnects, it need schedule the reconnect itself.

    :param convergence_loop_fsm: A convergence loop FSM as output by
    ``build_convergence_loop_fsm``.
    """
    return constructFiniteStateMachine(
        inputs=ClusterStatusInputs,
        outputs=ClusterStatusOutputs,
        states=ClusterStatusStates,
        initial=ClusterStatusStates.DISCONNECTED,
        table=_CLUSTER_STATUS_FSM_TABLE,
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
    # Sleep for a while (so we don't poll in a busy-loop).
    SLEEP = NamedConstant()
    # Stop sleeping:
    WAKEUP = NamedConstant()


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


@attributes(["delay_seconds"])
class _Sleep(trivialInput(ConvergenceLoopInputs.SLEEP)):
    """
    Sleep for given number of seconds.

    :ivar float delay_seconds: How many seconds to sleep.
    """
    @classmethod
    def with_jitter(cls, delay_seconds):
        """
        Add some noise to the delay, so sleeps aren't exactly the same across
        all processes.

        :param delay_seconds: How many seconds to sleep approximately.

        :return: ``_Sleep`` with jitter added.
        """
        jitter = 1 + uniform(-0.2, 0.2)
        return cls(delay_seconds=delay_seconds*jitter)


# How many seconds to sleep between iterations when we may yet not be
# converged so want to do another iteration again soon:

_UNCONVERGED_DELAY = 0.1
_UNCONVERGED_BACKOFF_FACTOR = 4


class _UnconvergedDelay(object):
    """
    Keep track of the next sleep duration while unconverged.

    When looping for convergence, we want to have exponential backoff
    in many situations. Instances of this class allow for the next sleep
    duration to be calculated.

    Call `sleep` to get a `_Sleep` instance for the next duration to sleep.
    This will also update the state to return a longer sleep next time.

    Calling `reset_delay` will mean that the next call to `sleep` will return
    `min_sleep`.
    """
    def __init__(self,
                 max_sleep=10,
                 min_sleep=_UNCONVERGED_DELAY):
        """
        Create an instance of `_UnconvergedDelay`.

        :param float max_sleep: the maximum duration for a `_Sleep` that
            `sleep` should return.
        :param float min_sleep: the duration for the `_Sleep` that will
             be returned from the first call to `sleep`, and calls
             immediately following a call to `reset_delay`.
        """
        self.max_sleep = max_sleep
        self.min_sleep = min_sleep
        self._delay = self.min_sleep

    def sleep(self):
        """
        Get the duration that should be slept for this iteration.

        :return _Sleep: an instance of `_Sleep` with a duration
            following an exponential backoff curve.
        """
        Message.log(
            message_type=u'flocker:node:_loop:delay',
            log_level=u'INFO',
            message=u'Intentionally delaying the next iteration of the '
                    u'convergence loop to avoid RequestLimitExceeded.',
            current_wait=self._delay
        )
        s = _Sleep(delay_seconds=self._delay)
        self._delay *= _UNCONVERGED_BACKOFF_FACTOR
        if self._delay > self.max_sleep:
            self._delay = self.max_sleep
        return s

    def reset_delay(self):
        """
        Reset the backoff algorithm so that the next call to `sleep`
        will return `min_sleep`.
        """
        self._delay = self.min_sleep


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
    # The loop is sleeping until the next iteration occurs:
    SLEEPING = NamedConstant()


class ConvergenceLoopOutputs(Names):
    """
    Converence loop FSM outputs.
    """
    # Store AMP client, desired configuration and cluster state for later
    # use:
    STORE_INFO = NamedConstant()
    # Start an iteration of the covergence loop:
    CONVERGE = NamedConstant()
    # Schedule timeout for sleep so we don't sleep forever:
    SCHEDULE_WAKEUP = NamedConstant()
    # Clear/cancel the sleep wakeup timeout:
    CLEAR_WAKEUP = NamedConstant()
    # Check if we need to wakeup due to update from AMP client:
    UPDATE_MAYBE_WAKEUP = NamedConstant()


_FIELD_CONNECTION = Field(
    u"connection",
    repr,
    u"The AMP connection to control service")

_FIELD_LOCAL_CHANGES = Field(
    u"local_changes", to_unserialized_json,
    u"Changes discovered in local state.")

LOG_SEND_TO_CONTROL_SERVICE = ActionType(
    u"flocker:agent:send_to_control_service",
    [_FIELD_CONNECTION, _FIELD_LOCAL_CHANGES], [],
    u"Send the local state to the control service.")

_FIELD_ACTIONS = Field(
    u"calculated_actions", repr,
    u"The actions we decided to take to converge with configuration.")

LOG_CONVERGE = ActionType(
    u"flocker:agent:converge",
    [], [],
    u"The convergence action within the loop.")

LOG_DISCOVERY = ActionType(
    u"flocker:agent:discovery", [], [Field(u"state", safe_repr)],
    u"The deployer is doing discovery of local state.")

LOG_CALCULATED_ACTIONS = MessageType(
    u"flocker:agent:converge:actions", [_FIELD_ACTIONS],
    u"The actions we're going to attempt.")


class ConvergenceLoop(object):
    """
    World object for the convergence loop state machine, executing the actions
    indicated by the outputs from the state machine.

    :ivar AMP client: An AMP client connected to the control
        service. Initially ``None``.

    :ivar Deployment configuration: Desired cluster
        configuration. Initially ``None``.

    :ivar DeploymentState cluster_state: Actual cluster state.  Initially
        ``None``.

    :ivar fsm: The finite state machine this is part of.

    :ivar _last_acknowledged_state: The last state that was sent to and
        acknowledged by the control service over the most recent connection
        to the control service.
    :type _last_acknowledged_state: tuple of IClusterStateChange

    :ivar _last_discovered_local_state: The discovered local state from
        last iteration done.

    :ivar _sleep_timeout: Current ``IDelayedCall`` for sleep timeout, or
        ``None`` if not in SLEEPING state.
    """
    def __init__(self, reactor, deployer):
        """
        :param IReactorTime reactor: Used to schedule delays in the loop.

        :param IDeployer deployer: Used to discover local state and calculate
            necessary changes to match desired configuration.
        """
        self.reactor = reactor
        self.deployer = deployer
        self.cluster_state = None
        self.client = None
        self._last_discovered_local_state = None
        self._last_acknowledged_state = None
        self._sleep_timeout = None
        self._unconverged_sleep = _UnconvergedDelay()

    def output_STORE_INFO(self, context):
        old_client = self.client
        self.client, self.configuration, self.cluster_state = (
            context.client, context.configuration, context.state)
        if old_client is not self.client:
            # State updates are now being sent somewhere else.  At least send
            # one update using the new client.
            self._last_acknowledged_state = None

    def output_UPDATE_MAYBE_WAKEUP(self, context):
        # External configuration and state has changed. Let's pretend
        # local state hasn't changed. If when we calculate changes that
        # still indicates some action should be taken that means we should
        # wake up:
        discovered = self._last_discovered_local_state
        try:
            changes = self.deployer.calculate_changes(
                self.configuration, self.cluster_state, discovered)
        except:
            # Something went wrong in calculation due to a bug in the
            # code. We should wake up just in case in order to be more
            # responsive.
            write_traceback()
            changes = None
        if not isinstance(changes, NoOp):
            self.fsm.receive(ConvergenceLoopInputs.WAKEUP)
        else:
            # Check if the calculated NoOp suggests an earlier wakeup than
            # currently planned:
            remaining = self._sleep_timeout.getTime() - self.reactor.seconds()
            calculated = changes.sleep.total_seconds()
            if calculated < remaining:
                self._sleep_timeout.reset(calculated)

    def _send_state_to_control_service(self, state_changes):
        context = LOG_SEND_TO_CONTROL_SERVICE(
            self.fsm.logger, connection=self.client,
            local_changes=list(state_changes),
        )
        with context.context():
            d = DeferredContext(self.client.callRemote(
                NodeStateCommand,
                state_changes=state_changes,
                eliot_context=context)
            )

            def record_acknowledged_state(ignored):
                self._last_acknowledged_state = state_changes

            def clear_acknowledged_state(failure):
                # We don't know if the control service has processed the update
                # or not. So we clear the last acknowledged state so that we
                # always send the state on the next iteration.
                self._last_acknowledged_state = None
                return failure

            d.addCallbacks(record_acknowledged_state, clear_acknowledged_state)
            d.addErrback(
                writeFailure, self.fsm.logger,
                u"Failed to send local state to control node.")
            return d.addActionFinish()

    def _maybe_send_state_to_control_service(self, state_changes):
        """
        If the given ``state_changes`` differ from those last acknowledged by
        the control service, send them to the control service.

        :param state_changes: State to send to the control service.
        :type state_changes: tuple of IClusterStateChange
        """
        if self._last_acknowledged_state != state_changes:
            return self._send_state_to_control_service(state_changes)
        else:
            return succeed(None)

    def output_CONVERGE(self, context):
        # XXX: We stopped logging configuration and cluster state here for
        # performance reasons.
        # But without some limited logging it'll be difficult to debug problems
        # all the way from a configuration change to the failed convergence
        # operation. FLOC-4331.
        with LOG_CONVERGE(self.fsm.logger).context():
            log_discovery = LOG_DISCOVERY(self.fsm.logger)
            with log_discovery.context():
                discover = DeferredContext(maybeDeferred(
                    self.deployer.discover_state, self.cluster_state,
                    persistent_state=self.configuration.persistent_state))

                def got_local_state(local_state):
                    log_discovery.addSuccessFields(state=local_state)
                    return local_state
                discover.addCallback(got_local_state)
                discover.addActionFinish()
            d = DeferredContext(discover.result)

        def got_local_state(local_state):
            self._last_discovered_local_state = local_state
            cluster_state_changes = local_state.shared_state_changes()
            # Current cluster state is likely out of date as regards the local
            # state, so update it accordingly.
            #
            # XXX This somewhat side-steps the whole explicit-state-machine
            # thing we're aiming for here.  It would be better for these state
            # changes to arrive as an input to the state machine.
            for state in cluster_state_changes:
                self.cluster_state = state.update_cluster_state(
                    self.cluster_state
                )

            # XXX And for this update to be the side-effect of an output
            # resulting.
            sent_state = self._maybe_send_state_to_control_service(
                cluster_state_changes)

            action = self.deployer.calculate_changes(
                self.configuration, self.cluster_state, local_state
            )
            if isinstance(action, NoOp):
                # If we have converged, we need to reset the sleep delay
                # in case there were any incremental back offs while
                # waiting to converge.
                self._unconverged_sleep.reset_delay()
                # We add some jitter so not all agents wake up at exactly
                # the same time, to reduce load on system:
                sleep_duration = _Sleep.with_jitter(
                    action.sleep.total_seconds())
            else:
                # We're going to do some work, we should do another
                # iteration, but chances are that if, for any reason,
                # the backend is saturated, by looping too fast, we
                # will only make things worse, so there is an incremental
                # back off in the sleep interval.
                sleep_duration = self._unconverged_sleep.sleep()

            LOG_CALCULATED_ACTIONS(calculated_actions=action).write(
                self.fsm.logger)
            ran_state_change = run_state_change(
                action,
                deployer=self.deployer,
                state_persister=RemoteStatePersister(client=self.client),
            )
            DeferredContext(ran_state_change).addErrback(
                writeFailure, self.fsm.logger)

            # Wait for the control node to acknowledge the new
            # state, and for the convergence actions to run.
            result = gather_deferreds([sent_state, ran_state_change])
            result.addCallback(lambda _: sleep_duration)
            return result
        d.addCallback(got_local_state)

        # If an error occurred we just want to log it and then try
        # converging again; hopefully next time we'll have more success.
        def error(failure):
            writeFailure(failure, self.fsm.logger)
            # We should retry to redo the failed work:
            return self._unconverged_sleep.sleep()
        d.addErrback(error)

        # We're done with the iteration:
        def send_delay_to_fsm(sleep):
            Message.log(
                message_type=u'flocker:node:_loop:CONVERGE:delay',
                log_level=u'INFO',
                message=u'Delaying until next convergence loop.',
                delay=sleep.delay_seconds
            )
            return self.fsm.receive(sleep)

        d.addCallback(send_delay_to_fsm)
        d.addActionFinish()

    def output_SCHEDULE_WAKEUP(self, context):
        self._sleep_timeout = self.reactor.callLater(
            context.delay_seconds,
            lambda: self.fsm.receive(ConvergenceLoopInputs.WAKEUP))

    def output_CLEAR_WAKEUP(self, context):
        if self._sleep_timeout.active():
            self._sleep_timeout.cancel()
        self._sleep_timeout = None


def _build_convergence_loop_table():
    """
    Create the ``TransitionTable`` needed by the convergence loop FSM.

    :return TransitionTable: The transition table for the state machine for
        converging on the cluster configuration.
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
            I.SLEEP: ([O.SCHEDULE_WAKEUP], S.SLEEPING),
        })
    table = table.addTransitions(
        S.CONVERGING_STOPPING, {
            I.STATUS_UPDATE: ([O.STORE_INFO], S.CONVERGING),
            I.SLEEP: ([], S.STOPPED),
        })
    table = table.addTransitions(
        S.SLEEPING, {
            I.WAKEUP: ([O.CLEAR_WAKEUP, O.CONVERGE], S.CONVERGING),
            I.STOP: ([O.CLEAR_WAKEUP], S.STOPPED),
            I.STATUS_UPDATE: (
                [O.STORE_INFO, O.UPDATE_MAYBE_WAKEUP], S.SLEEPING),
            })
    return table


_CONVERGENCE_LOOP_FSM_TABLE = _build_convergence_loop_table()


def build_convergence_loop_fsm(reactor, deployer):
    """
    Create a convergence loop FSM.

    Once cluster config+cluster state updates from control service are
    received the basic loop is:

    1. Discover local state.
    2. Calculate ``IStateChanges`` based on local state and cluster
       configuration and cluster state we received from control service.
    3. Execute the change.
    4. Sleep.

    However, if an update is received during sleep then we calculate based
    on that updated config+state whether a ``IStateChange`` needs to
    happen. If it does that means this change will have impact on what we
    do, so we interrupt the sleep. If calculation suggests a no-op then we
    keep sleeping. Notably we do **not** do a discovery of local state
    when an update is received while sleeping, since that is an expensive
    operation that can involve talking to external resources. Moreover an
    external update only implies external state/config changed, so we're
    not interested in the latest local state in trying to decide if this
    update requires us to do something; a recently cached version should
    suffice.

    :param IReactorTime reactor: Used to schedule delays in the loop.

    :param IDeployer deployer: Used to discover local state and calcualte
        necessary changes to match desired configuration.
    """
    loop = ConvergenceLoop(reactor, deployer)
    fsm = constructFiniteStateMachine(
        inputs=ConvergenceLoopInputs,
        outputs=ConvergenceLoopOutputs,
        states=ConvergenceLoopStates,
        initial=ConvergenceLoopStates.STOPPED,
        table=_CONVERGENCE_LOOP_FSM_TABLE,
        richInputs=[_ClientStatusUpdate, _Sleep],
        inputContext={},
        world=MethodSuffixOutputer(loop))
    loop.fsm = fsm
    return fsm


@implementer(IStatePersister)
class RemoteStatePersister(PClass):
    """
    Persistence implementation that uses the agent connection to record state
    on the control node.

    :ivar AMP client: The client connected to the control node.
    """
    client = field(mandatory=True)

    def record_ownership(self, dataset_id, blockdevice_id):
        return self.client.callRemote(
            SetBlockDeviceIdForDatasetId,
            dataset_id=unicode(dataset_id),
            blockdevice_id=blockdevice_id,
        )


@implementer(IConvergenceAgent)
@attributes(["reactor", "deployer", "host", "port", "era"])
class AgentLoopService(MultiService, object):
    """
    Service in charge of running the convergence loop.

    :ivar reactor: The reactor.
    :ivar IDeployer deployer: Deployer for discovering local state and
            then changing it.
    :ivar host: Host to connect to.
    :ivar port: Port to connect to.
    :ivar cluster_status: A cluster status FSM.
    :ivar factory: The factory used to connect to the control service.
    :ivar reconnecting_factory: The underlying factory used to connect to
        the control service, without the TLS wrapper.
    :ivar UUID era: This node's era.
    """

    def __init__(self, context_factory):
        """
        :param context_factory: TLS context factory for the AMP client.
        """
        MultiService.__init__(self)
        convergence_loop = build_convergence_loop_fsm(
            self.reactor, self.deployer
        )
        self.logger = convergence_loop.logger
        self.cluster_status = build_cluster_status_fsm(convergence_loop)
        self.reconnecting_factory = ReconnectingClientFactory.forProtocol(
            lambda: AgentAMP(self.reactor, self)
        )
        self.factory = TLSMemoryBIOFactory(context_factory, True,
                                           self.reconnecting_factory)

    def startService(self):
        MultiService.startService(self)
        self.reactor.connectTCP(self.host, self.port, self.factory)

    def stopService(self):
        MultiService.stopService(self)
        self.reconnecting_factory.stopTrying()
        self.cluster_status.receive(ClusterStatusInputs.SHUTDOWN)

    # IConvergenceAgent methods:

    def connected(self, client):
        # Reduce reconnect delay back to normal, since we've successfully
        # connected:
        self.reconnecting_factory.resetDelay()
        d = client.callRemote(SetNodeEraCommand,
                              era=unicode(self.era),
                              node_uuid=unicode(self.deployer.node_uuid))
        d.addErrback(writeFailure)
        self.cluster_status.receive(_ConnectedToControlService(client=client))

    def disconnected(self):
        self.cluster_status.receive(
            ClusterStatusInputs.DISCONNECTED_FROM_CONTROL_SERVICE)

    def cluster_updated(self, configuration, cluster_state):
        # Filter out state for this node if the era doesn't match. Since
        # the era doesn't match ours that means it's old pre-reboot state
        # that hasn't expired yet and is likely wrong, so we don't want to
        # act based on any information in it.
        node_uuid = self.deployer.node_uuid
        if self.era != cluster_state.node_uuid_to_era.get(node_uuid):
            cluster_state = cluster_state.remove_node(node_uuid)
        self.cluster_status.receive(_StatusUpdate(configuration=configuration,
                                                  state=cluster_state))
