# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Communication protocol between control service and convergence agent.

The cluster is composed of a control service server, and convergence
agents. The code below implicitly assumes convergence agents are
node-specific, but that will likely change and involve additinal commands.

Interactions:

* The control service knows the desired configuration for the cluster.
  Every time the configuration changes the control service notifies the
  convergence agents using the ``ClusterStatusCommand``.

* The convergence agents can determine part of the state of the cluster
  (usually their own local state).  Whenever node state changes they notify
  the control service with a ``NodeStateCommand``.

* The control service caches the most recent state from all nodes.  Whenever
  the control service receives an update to the state of a specific node via a
  ``NodeStateCommand``, the control service integrates that update into a
  cluster-wide state representation (the state of all of the nodes) and sends a
  ``ClusterStatusCommand`` to all convergence agents.

Eliot contexts are transferred along with AMP commands, allowing tracing
of logged actions across processes (see
http://eliot.readthedocs.org/en/0.6.0/threads.html).

:var _wire_encode_cache: ``LRUCache`` mapping serializable objects to
    their ``wire_encode`` output.
"""

from datetime import timedelta
from io import BytesIO
from itertools import count
from twisted.internet.defer import maybeDeferred
from uuid import UUID

from eliot import (
    Logger, ActionType, Action, Field, MessageType,
)
from eliot.twisted import DeferredContext

from pyrsistent import PClass, field

from repoze.lru import LRUCache

from characteristic import with_cmp

from zope.interface import Interface, Attribute

from twisted.application.service import Service
from twisted.protocols.amp import (
    Argument, Command, Integer, CommandLocator, AMP, Unicode,
    MAX_VALUE_LENGTH,
)
from twisted.internet.task import LoopingCall
from twisted.internet.protocol import ServerFactory
from twisted.application.internet import StreamServerEndpointService
from twisted.protocols.tls import TLSMemoryBIOFactory

from ._persistence import wire_encode, wire_decode
from ._model import (
    Deployment, DeploymentState, ChangeSource, UpdateNodeStateEra,
)

PING_INTERVAL = timedelta(seconds=30)


class Big(Argument):
    """
    An ``Argument`` type which can handle objects which are larger than AMP's
    MAX_VALUE_LENGTH when serialized.

    Thanks to Glyph Lefkowitz for the idea:
    * http://bazaar.launchpad.net/~glyph/+junk/amphacks/view/head:/python/amphacks/mediumbox.py  # noqa
    """
    def __init__(self, another_argument):
        """
        :param Argument another_argument: The wrapped AMP ``Argument``.
        """
        self.another_argument = another_argument

    def toBox(self, name, strings, objects, proto):
        """
        During serialization, the wrapped ``Argument`` is serialized in full
        and then popped out of the supplied ``strings`` dictionary, broken into
        chunks <= MAX_VALUE_LENGTH which are added back to the ``strings``
        dictionary with indexed key names so that the chunks can be put back
        together in the correct order during deserialization.

        See ``IArgumentType`` for argument and return type documentation.
        """
        self.another_argument.toBox(name, strings, objects, proto)
        value = BytesIO(strings.pop(name))
        counter = 0
        while True:
            nextChunk = value.read(MAX_VALUE_LENGTH)
            if not nextChunk:
                break
            strings["%s.%d" % (name, counter)] = nextChunk
            counter += 1

    def fromBox(self, name, strings, objects, proto):
        """
        During deserialization, the indexed chunks are re-assembled from the
        ``strings`` dictionary and the combined value is then placed back into
        the strings dictionary using the expected key name. The ``fromBox``
        method of the wrapped ``Argument`` is then called supplied with the
        updated ``strings`` dictionary, deserializes the large value and
        populates the ``objects`` dictionary with the result.

        See ``IArgumentType`` for argument and return type documentation.
        """

        value = BytesIO()
        for counter in count(0):
            chunk = strings.get("%s.%d" % (name, counter))
            if chunk is None:
                break
            value.write(chunk)
            strings[name] = value.getvalue()
        self.another_argument.fromBox(name, strings, objects, proto)


# The configuration and state can get pretty big, so don't want too many:
_wire_encode_cache = LRUCache(50)


def caching_wire_encode(obj):
    """
    Encode an object to bytes using ``wire_encode`` and cache the result,
    or return cached result if available.

    This relies on cached objects being immutable, or at least not being
    modified. Given our usage patterns that is currently the case and
    should continue to be, but worth keeping in mind.

    :param obj: Object to encode.
    :return: Resulting ``bytes``.
    """
    result = _wire_encode_cache.get(obj)
    if result is None:
        result = wire_encode(obj)
        _wire_encode_cache.put(obj, result)
    return result


class SerializableArgument(Argument):
    """
    AMP argument that takes an object that can be serialized by the
    configuration persistence layer.
    """
    def __init__(self, *classes):
        """
        :param *classes: The type or types of the objects we expect to
            (de)serialize. Only immutable types should be used if encoding
            caching will be enabled.
        """
        Argument.__init__(self)
        self._expected_classes = classes

    def fromString(self, in_bytes):
        obj = wire_decode(in_bytes)
        if not isinstance(obj, self._expected_classes):
            raise TypeError(
                "{} is none of {}".format(obj, self._expected_classes)
            )
        return obj

    def toString(self, obj):
        if not isinstance(obj, self._expected_classes):
            raise TypeError(
                "{} is none of {}".format(obj, self._expected_classes)
            )
        return caching_wire_encode(obj)


class _EliotActionArgument(Unicode):
    """
    AMP argument that serializes/deserializes Eliot actions.
    """
    def fromStringProto(self, inString, proto):
        return Action.continue_task(
            proto.logger,
            Unicode.fromStringProto(self, inString, proto))

    def toString(self, inObject):
        return inObject.serialize_task_id()


class VersionCommand(Command):
    """
    Return configuration protocol version of the control service.

    Semantic versioning: Major version changes implies incompatibility.
    """
    arguments = []
    response = [('major', Integer())]


class NoOp(Command):
    """
    Do nothing.  Return nothing.  This merely generates some traffic on the
    connection to support timely disconnection notification.

    No-ops are one-way to force both sides to send them of their own volition
    so that both sides will receive timely disconnection notification.
    """
    requiresAnswer = False


class ClusterStatusCommand(Command):
    """
    Used by the control service to inform a convergence agent of the
    latest cluster state and desired configuration.

    Having both as a single command simplifies the decision making process
    in the convergence agent during startup.
    """
    arguments = [('configuration', Big(SerializableArgument(Deployment))),
                 ('state', Big(SerializableArgument(DeploymentState))),
                 ('eliot_context', _EliotActionArgument())]
    response = []


class SetNodeEraCommand(Command):
    """
    Tell the control service the current era for a node.

    This should clear any previous NodeState that has a different
    era. Updates to the node should only be sent after this command, to
    ensure it doesn't get stale pre-reboot information (i.e. NodeState
    with wrong era).
    """
    arguments = [('era', Unicode()),
                 ('node_uuid', Unicode())]
    response = []


class NodeStateCommand(Command):
    """
    Used by a convergence agent to update the control service about the
    status of a particular node.
    """
    arguments = [
        # A state change might be large enough not to fit into a single AMP
        # value so use Big to split it across multiple values if necessary.
        #
        # The protocol specifies that a sequence of changes is always sent so
        # the type required by ``SerializableArgument`` is either ``list`` or
        # ``tuple`` (the implementation mostly or always uses a ``tuple`` but
        # ``SerializableArgument`` converts ``tuple`` to ``list`` so we have to
        # allow both types so the *receiving* side, where that conversion has
        # happened, accepts the value).
        #
        # The sequence items will be some other serializable type (and should
        # be a type that implements ``IClusterStateSource`` - such as
        # ``NodeState`` or ``NonManifestDatasets``) and ``wire_encode`` will
        # enforce that for us.
        #
        # Note that Big is not a great way to deal with large quantities of
        # data.  See FLOC-3113.
        ('state_changes', Big(SerializableArgument(list, tuple))),
        ('eliot_context', _EliotActionArgument()),
    ]
    response = []


class Timeout(object):
    """
    Call the specified action after the specified delay in seconds.
    """
    def __init__(self, reactor, timeout, action):
        """
        :param IReactorTime reactor: A reactor to use to control when
            the action is called.
        :param int timeout: Interval in seconds to trigger the action.
        :param callable action: The function to execute upon reaching the
            timeout.
        """
        self._delay_call = reactor.callLater(timeout, action)
        self._timeout = timeout

    def reset(self):
        """
        Reset the delayed call to this ``Timeout``'s ``action``.
        """
        self._delay_call.reset(self._timeout)


class ControlServiceLocator(CommandLocator):
    """
    Control service side of the protocol.

    :ivar IClusterStateSource _source: The change source uniquely representing
        the AMP connection for which this locator is being used.
    :ivar _reactor: See ``reactor`` parameter of ``__init__``
    """
    def __init__(self, reactor, control_amp_service, timeout):
        """
        :param IReactorTime reactor: A reactor to use to tell the time for
            activity/inactivity reporting.
        :param ControlAMPService control_amp_service: The service managing AMP
            connections to the control service.
        :param Timeout timeout: A ``Timeout`` object to reset when a message
            is received.
        """
        CommandLocator.__init__(self)

        # Create a brand new source to associate with changes from this
        # particular connection from an agent.  The lifetime of the source
        # exactly matches the lifetime of the protocol.  This is good since
        # after the connection is lost we can't receive any more changes from
        # it.
        self._source = ChangeSource()
        self._timeout = timeout

        self._reactor = reactor
        self.control_amp_service = control_amp_service

    def locateResponder(self, name):
        """
        Do normal responder lookup, reset the connection timeout and record
        this activity.
        """
        self._timeout.reset()
        self._source.set_last_activity(self._reactor.seconds())
        return CommandLocator.locateResponder(self, name)

    @property
    def logger(self):
        return self.control_amp_service.logger

    @NoOp.responder
    def noop(self):
        """
        Perform no operation.
        """
        return {}

    @VersionCommand.responder
    def version(self):
        return {"major": 1}

    @NodeStateCommand.responder
    def node_changed(self, eliot_context, state_changes):
        with eliot_context:
            self.control_amp_service.node_changed(
                self._source, state_changes,
            )
            return {}

    @SetNodeEraCommand.responder
    def set_node_era(self, era, node_uuid):
        # Further work will be done in FLOC-3380
        self.control_amp_service.cluster_state.apply_changes_from_source(
            self._source, [UpdateNodeStateEra(era=UUID(era),
                                              uuid=UUID(node_uuid))])
        # We don't bother sending an update to other nodes because this
        # command will immediately be followed by a ``NodeStateCommand``
        # with more interesting information.
        return {}


def timeout_for_protocol(reactor, protocol):
    """
    Create a timeout for inactive AMP connections that will abort the
    connection when the timeout is reached.

    :param IReactorTime reactor: A reactor to use to control when
        the action is called.
    :param AMP protocol: The protocol on which inactive connections will
        be aborted.
    """
    return Timeout(reactor, 2 * PING_INTERVAL.seconds,
                   lambda: protocol.transport.abortConnection())


class ControlAMP(AMP):
    """
    AMP protocol for control service server.

    :ivar Pinger _pinger: Helper which periodically pings this protocol's peer
        to verify it's still alive.
    """
    def __init__(self, reactor, control_amp_service):
        """
        :param reactor: See ``ControlServiceLocator.__init__``.
        :param ControlAMPService control_amp_service: The service managing AMP
            connections to the control service.
        """
        locator = ControlServiceLocator(reactor, control_amp_service,
                                        timeout_for_protocol(reactor, self))
        AMP.__init__(self, locator=locator)

        self.control_amp_service = control_amp_service
        self._pinger = Pinger(reactor)

    def connectionMade(self):
        AMP.connectionMade(self)
        self.control_amp_service.connected(self)
        self._pinger.start(self, PING_INTERVAL)

    def connectionLost(self, reason):
        AMP.connectionLost(self, reason)
        self.control_amp_service.disconnected(self)
        self._pinger.stop()


# These two logging fields use caching_wire_encode as the serializer so
# that they can share the encoding cache with the network code related to
# this logging.  This reduces the overhead of logging these (potentially
# quite large) data structures.
DEPLOYMENT_CONFIG = Field(u"configuration", caching_wire_encode,
                          u"The cluster configuration")
CLUSTER_STATE = Field(u"state", caching_wire_encode, u"The cluster state")

LOG_SEND_CLUSTER_STATE = ActionType(
    "flocker:controlservice:send_cluster_state",
    [],
    [DEPLOYMENT_CONFIG, CLUSTER_STATE],
    "Send the configuration and state of the cluster to all agents.")


def _serialize_agent(controlamp):
    """
    Serialize a connected ``ControlAMP`` to the address of its peer.

    :return: A string representation of the Twisted address object describing
        the remote address of the connection of the given protocol.

    :rtype str:
    """
    return str(controlamp.transport.getPeer())


AGENT = Field(
    u"agent", _serialize_agent, u"The agent we're sending to",
)

LOG_SEND_TO_AGENT = ActionType(
    "flocker:controlservice:send_state_to_agent",
    [AGENT],
    [],
    "Send the configuration and state of the cluster to a specific agent.")

AGENT_CONNECTED = ActionType(
    "flocker:controlservice:agent_connected",
    [AGENT],
    [],
    "An agent connected to the control service."
)

AGENT_UPDATE_ELIDED = MessageType(
    "flocker:controlservice:agent_update_elided",
    [AGENT],
    u"An update to an agent was elided because a subsequent update supercedes "
    u"it.",
)

AGENT_UPDATE_DELAYED = MessageType(
    "flocker:controlservice:agent_update_delayed",
    [AGENT],
    u"An update to an agent was delayed because an earlier update is still in "
    u"progress.",
)


class _UpdateState(PClass):
    """
    Represent the state related to sending a ``ClusterStatusCommand`` to an
    agent.

    :ivar response: The pending result of an update that is in progress.
    :ivar scheduled: ``True`` if another update should be performed as soon as
        the current one is done, ``False`` otherwise.
    """
    response = field()
    next_scheduled = field()


class ControlAMPService(Service):
    """
    Control Service AMP server.

    Convergence agents connect to this server.

    :ivar dict _current_command: A dictionary containing information about
        connections to which state updates are currently in progress.  The keys
        are protocol instances.  The values are ``_UpdateState`` instances.
    """
    logger = Logger()

    def __init__(self, reactor, cluster_state, configuration_service, endpoint,
                 context_factory):
        """
        :param reactor: See ``ControlServiceLocator.__init__``.
        :param ClusterStateService cluster_state: Object that records known
            cluster state.
        :param ConfigurationPersistenceService configuration_service:
            Persistence service for desired cluster configuration.
        :param endpoint: Endpoint to listen on.
        :param context_factory: TLS context factory.
        """
        self.connections = set()
        self._current_command = {}
        self.cluster_state = cluster_state
        self.configuration_service = configuration_service
        self.endpoint_service = StreamServerEndpointService(
            endpoint,
            TLSMemoryBIOFactory(
                context_factory,
                False,
                ServerFactory.forProtocol(lambda: ControlAMP(reactor, self))
            )
        )
        # When configuration changes, notify all connected clients:
        self.configuration_service.register(
            lambda: self._send_state_to_connections(self.connections))

    def startService(self):
        self.endpoint_service.startService()

    def stopService(self):
        self.endpoint_service.stopService()
        for connection in self.connections:
            connection.transport.loseConnection()

    def _send_state_to_connections(self, connections):
        """
        Send desired configuration and cluster state to all given connections.

        :param connections: A collection of ``AMP`` instances.
        """
        configuration = self.configuration_service.get()
        state = self.cluster_state.as_deployment()

        # Connections are separated into three groups to support a scheme which
        # lets us avoid sending certain updates which we know are not
        # necessary.  This reduces traffic and associated costs (CPU, memory).
        #
        # Other schemes are possible and might produce even better performance.
        # See https://clusterhq.atlassian.net/browse/FLOC-3140 for some
        # brainstorming.

        # Collect connections for which there is currently no unacknowledged
        # update.  These can receive a new update right away.
        can_update = []

        # Collect connections for which there is an unacknowledged update.
        # Since something has changed, these should receive another update once
        # that acknowledgement is received.
        delayed_update = []

        # Collect connections which were already set to receive a delayed
        # update and still haven't sent an acknowledgement.  These will still
        # receive a delayed update but we'll also note that we're going to skip
        # sending one intermediate update to them.
        elided_update = []

        for connection in connections:
            try:
                update = self._current_command[connection]
            except KeyError:
                # There's nothing in the tracking state for this connection.
                # That means there's no unacknowledged update.  That means we
                # can send another update right away.
                can_update.append(connection)
            else:
                # These connections do currently have an unacknowledged update
                # outstanding.
                if update.next_scheduled:
                    # And these connections are also already scheduled to
                    # receive another update after the one they're currently
                    # processing.  That update will include the most up-to-date
                    # information so we're effectively skipping an update
                    # that's no longer useful.
                    elided_update.append(connection)
                else:
                    # These don't have another update scheduled yet so we'll
                    # schedule one.
                    delayed_update.append(connection)

        # Make sure to run the logging action inside the caching block.
        # This lets encoding for logging share the cache with encoding for
        # network traffic.
        with LOG_SEND_CLUSTER_STATE() as action:
            if can_update:
                # If there are any protocols that can be updated right now,
                # we also want to see what updates they receive.  Since
                # logging shares the caching context, it shouldn't be any
                # more expensive to serialize this information into the log
                # now.  We specifically avoid logging this information if
                # no protocols are being updated because the serializing is
                # more expensive in that case and at the same time that
                # information isn't actually useful.
                action.add_success_fields(
                    configuration=configuration, state=state
                )
            else:
                # Eliot wants those fields though.
                action.add_success_fields(configuration=None, state=None)

            for connection in can_update:
                self._update_connection(connection, configuration, state)

            for connection in elided_update:
                AGENT_UPDATE_ELIDED(agent=connection).write()

            for connection in delayed_update:
                self._delayed_update_connection(connection)

    def _update_connection(self, connection, configuration, state):
        """
        Send a ``ClusterStatusCommand`` to an agent.

        :param ControlAMP connection: The connection to use to send the
            command.

        :param Deployment configuration: The cluster configuration to send.
        :param DeploymentState state: The current cluster state to send.
        """
        action = LOG_SEND_TO_AGENT(agent=connection)
        with action.context():
            # Use ``maybeDeferred`` so if an exception happens,
            # it will be wrapped in a ``Failure`` - see FLOC-3221
            d = DeferredContext(maybeDeferred(
                connection.callRemote,
                ClusterStatusCommand,
                configuration=configuration,
                state=state,
                eliot_context=action
            ))
            d.addActionFinish()
            d.result.addErrback(lambda _: None)

        update = self._current_command[connection] = _UpdateState(
            response=d.result,
            next_scheduled=False,
        )

        def finished_update(ignored):
            del self._current_command[connection]
        update.response.addCallback(finished_update)

    def _delayed_update_connection(self, connection):
        """
        Send a ``ClusterStatusCommand`` to an agent after it has acknowledged
        the last one.

        :param ControlAMP connection: The connection to use to send the
            command.  This connection is expected to have previously been sent
            such a command and to not yet have acknowledged it.  Internal state
            related to this will be used and then updated.
        """
        AGENT_UPDATE_DELAYED(agent=connection).write()
        update = self._current_command[connection]
        update.response.addCallback(
            lambda ignored: self._send_state_to_connections([connection]),
        )
        self._current_command[connection] = update.set(next_scheduled=True)

    def connected(self, connection):
        """
        A new connection has been made to the server.

        :param ControlAMP connection: The new connection.
        """
        with AGENT_CONNECTED(agent=connection):
            self.connections.add(connection)
            self._send_state_to_connections([connection])

    def disconnected(self, connection):
        """
        An existing connection has been disconnected.

        :param ControlAMP connection: The lost connection.
        """
        self.connections.remove(connection)

    def node_changed(self, source, state_changes):
        """
        We've received a node state update from a connected client.

        :param IClusterStateSource source: Representation of where these
            changes were received from.
        :param list state_changes: One or more ``IClusterStateChange``
            providers representing the state change which has taken place.
        """
        self.cluster_state.apply_changes_from_source(source, state_changes)
        self._send_state_to_connections(self.connections)


class IConvergenceAgent(Interface):
    """
    The agent that will receive notifications from control service.
    """
    logger = Attribute("An eliot ``Logger``.")

    def connected(client):
        """
        The client has connected to the control service.

        :param AgentClient client: The connected client.
        """

    def disconnected():
        """
        The client has disconnected from the control service.
        """

    def cluster_updated(configuration, cluster_state):
        """
        The cluster's desired configuration or actual state have changed.

        :param Deployment configuration: The desired configuration for the
            cluster.

        :param Deployment cluster_state: The current state of the
            cluster. Mostly useful for what it tells the agent about
            non-local state, since the agent's knowledge of local state is
            canonical.
        """


@with_cmp(["agent"])
class _AgentLocator(CommandLocator):
    """
    Command locator for convergence agent.
    """
    def __init__(self, agent, timeout):
        """
        :param IConvergenceAgent agent: Convergence agent to notify of changes.
        :param Timeout timeout: A ``Timeout`` object to reset when a message
            is received.
        """
        CommandLocator.__init__(self)
        self.agent = agent
        self._timeout = timeout

    def locateResponder(self, name):
        """
        Do normal responder lookup and reset the connection timeout.
        """
        self._timeout.reset()
        return CommandLocator.locateResponder(self, name)

    @NoOp.responder
    def noop(self):
        """
        Perform no operation.
        """
        return {}

    @property
    def logger(self):
        """
        The ``Logger`` to use for Eliot logging.
        """
        return self.agent.logger

    @ClusterStatusCommand.responder
    def cluster_updated(self, eliot_context, configuration, state):
        with eliot_context:
            self.agent.cluster_updated(configuration, state)
            return {}


class AgentAMP(AMP):
    """
    AMP protocol for convergence agent side of the protocol.

    This is the client protocol that will connect to the control service.

    :ivar Pinger _pinger: Helper which periodically pings this protocol's peer
        to verify it's still alive.
    """
    def __init__(self, reactor, agent):
        """
        :param IReactorTime reactor: A reactor to use to schedule periodic ping
            operations.root@52.28.55.192
        :param IConvergenceAgent agent: Convergence agent to notify of changes.
        """
        locator = _AgentLocator(agent, timeout_for_protocol(reactor, self))
        AMP.__init__(self, locator=locator)
        self.agent = agent
        self._pinger = Pinger(reactor)

    def connectionMade(self):
        AMP.connectionMade(self)
        self.agent.connected(self)
        self._pinger.start(self, PING_INTERVAL)

    def connectionLost(self, reason):
        AMP.connectionLost(self, reason)
        self.agent.disconnected()
        self._pinger.stop()


class Pinger(object):
    """
    An periodic AMP ping helper.
    """
    def __init__(self, reactor):
        """
        :param IReactorTime reactor: The reactor to use to schedule the pings.
        """
        self.reactor = reactor

    def start(self, protocol, interval):
        """
        Start sending some pings.

        :param AMP protocol: The protocol over which to send the pings.
        :param timedelta interval: The interval at which to send the pings.
        """
        def ping():
            protocol.callRemote(NoOp)
        self._pinging = LoopingCall(ping)
        self._pinging.clock = self.reactor
        self._pinging.start(interval.total_seconds(), now=False)

    def stop(self):
        """
        Stop sending the pings.
        """
        self._pinging.stop()
