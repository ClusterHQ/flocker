# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Communication protocol between control service and convergence agent.

THIS CODE IS INSECURE AND SHOULD NOT BE DEPLOYED IN ANY FORM UNTIL
https://clusterhq.atlassian.net/browse/FLOC-1241 IS FIXED.

The cluster is composed of a control service server, and convergence
agents. The code below implicitly assumes convergence agents are
node-specific, but that will likely change and involve additinal commands.

Interactions:

* The control service knows the desired configuration for the cluster.
  Every time it changes it notifies the convergence agents using the
  ClusterStatusCommand.
* The convergence agents know the state of nodes. Whenever node state
  changes they notify the control service with a NodeStateCommand.
* The control service caches the current state of all nodes. Whenever the
  control service receives an update to the state of a specific node via a
  NodeStateCommand, the control service then aggregates that update with
  the rest of the nodes' state and sends a ClusterStatusCommand to all
  convergence agents.
"""

from characteristic import with_cmp

from zope.interface import Interface

from twisted.application.service import Service
from twisted.protocols.amp import (
    Argument, Command, Integer, CommandLocator, AMP,
)
from twisted.internet.protocol import ServerFactory
from twisted.application.internet import StreamServerEndpointService

from ._persistence import wire_encode, wire_decode
from ._model import Deployment, NodeState


class SerializableArgument(Argument):
    """
    AMP argument that takes an object that can be serialized by the
    configuration persistence layer.
    """
    def __init__(self, cls):
        """
        :param cls: The type of the objects we expect to (de)serialize.
        """
        Argument.__init__(self)
        self._expected_class = cls

    def fromString(self, in_bytes):
        obj = wire_decode(in_bytes)
        if not isinstance(obj, self._expected_class):
            raise TypeError("{} is not a {}".format(obj, self._expected_class))
        return obj

    def toString(self, obj):
        if not isinstance(obj, self._expected_class):
            raise TypeError("{} is not a {}".format(obj, self._expected_class))
        return wire_encode(obj)


class VersionCommand(Command):
    """
    Return configuration protocol version of the control service.

    Semantic versioning: Major version changes implies incompatibility.
    """
    arguments = []
    response = [('major', Integer())]


class ClusterStatusCommand(Command):
    """
    Used by the control service to inform a convergence agent of the
    latest cluster state and desired configuration.

    Having both as a single command simplifies the decision making process
    in the convergence agent during startup.
    """
    arguments = [('configuration', SerializableArgument(Deployment)),
                 ('state', SerializableArgument(Deployment))]
    response = []


class NodeStateCommand(Command):
    """
    Used by a convergence agent to update the control service about the
    status of a particular node.
    """
    arguments = [('node_state', SerializableArgument(NodeState))]
    response = []


class ControlServiceLocator(CommandLocator):
    """
    Control service side of the protocol.
    """
    def __init__(self, control_amp_service):
        """
        :param ControlAMPService control_amp_service: The service managing AMP
             connections to the control service.
        """
        CommandLocator.__init__(self)
        self.control_amp_service = control_amp_service

    @VersionCommand.responder
    def version(self):
        return {"major": 1}

    @NodeStateCommand.responder
    def node_changed(self, node_state):
        self.control_amp_service.node_changed(node_state)
        return {}


class ControlAMP(AMP):
    """
    AMP protocol for control service server.
    """
    def __init__(self, control_amp_service):
        """
        :param ControlAMPService control_amp_service: The service managing AMP
             connections to the control service.
        """
        AMP.__init__(self, locator=ControlServiceLocator(control_amp_service))
        self.control_amp_service = control_amp_service

    def connectionMade(self):
        AMP.connectionMade(self)
        self.control_amp_service.connected(self)

    def connectionLost(self, reason):
        AMP.connectionLost(self, reason)
        self.control_amp_service.disconnected(self)


class ControlAMPService(Service):
    """
    Control Service AMP server.

    Convergence agents connect to this server.
    """
    def __init__(self, cluster_state, configuration_service, endpoint):
        """
        :param ClusterStateService cluster_state: Object that records known
            cluster state.
        :param ConfigurationPersistenceService configuration_service:
            Persistence service for desired cluster configuration.
        :param endpoint: Endpoint to listen on.
        """
        self.connections = set()
        self.cluster_state = cluster_state
        self.configuration_service = configuration_service
        self.endpoint_service = StreamServerEndpointService(
            endpoint, ServerFactory.forProtocol(lambda: ControlAMP(self)))
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
        for connection in connections:
            connection.callRemote(ClusterStatusCommand,
                                  configuration=configuration,
                                  state=state)
            # Handle errors from callRemote by logging them
            # https://clusterhq.atlassian.net/browse/FLOC-1311

    def connected(self, connection):
        """
        A new connection has been made to the server.

        :param ControlAMP connection: The new connection.
        """
        self.connections.add(connection)
        self._send_state_to_connections([connection])

    def disconnected(self, connection):
        """
        An existing connection has been disconnected.

        :param ControlAMP connection: The lost connection.
        """
        self.connections.remove(connection)

    def node_changed(self, node_state):
        """
        We've received a node state update from a connected client.

        :param bytes hostname: The hostname of the node.
        :param NodeState node_state: The changed state for the node.
        """
        self.cluster_state.update_node_state(node_state)
        self._send_state_to_connections(self.connections)


class IConvergenceAgent(Interface):
    """
    The agent that will receive notifications from control service.
    """
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
    def __init__(self, agent):
        """
        :param IConvergenceAgent agent: Convergence agent to notify of changes.
        """
        CommandLocator.__init__(self)
        self.agent = agent

    @ClusterStatusCommand.responder
    def cluster_updated(self, configuration, state):
        self.agent.cluster_updated(configuration, state)
        return {}


class AgentAMP(AMP):
    """
    AMP protocol for convergence agent side of the protocol.

    This is the client protocol that will connect to the control service.
    """
    def __init__(self, agent):
        """
        :param IConvergenceAgent agent: Convergence agent to notify of changes.
        """
        locator = _AgentLocator(agent)
        AMP.__init__(self, locator=locator)
        self.agent = agent

    def connectionMade(self):
        AMP.connectionMade(self)
        self.agent.connected(self)

    def connectionLost(self, reason):
        AMP.connectionLost(self, reason)
        self.agent.disconnected()
