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

from pickle import dumps, loads

from twisted.protocols.amp import Argument, Command, Integer, String

from .._model import NodeState, Deployment
from ._persistence import serialize_deployment, deserialize_deployment


class NodeStateArgument(Argument):
    """
    AMP argument that takes a ``NodeState`` object.
    """
    def fromString(self, in_bytes):
        #return loads(in_bytes)
        pass

    def toString(self, node_state):
        #return dumps(node_state)
        pass


# XXX This should suffice for both both communicating global current state
# and the deployment configuration from control service to convergence
# agent. We don't need to transfer used ports because the control service
# will be the one to assign ports for links.
class DeploymentArgument(Argument):
    """
    AMP argument that takes a ``Deployment`` object.
    """
    def fromString(self, in_bytes):
        #return deserialize_deployment(in_bytes)

    def toString(self, deployment):
        #return serialize_deployment(node_state)
        pass


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
    arguments = [('configuration', DeploymentArgument()),
                 ('state', DeploymentArgument())]
    response = []


class NodeStateCommand(Command):
    """
    Used by a convergence agent to update the control service about the
    status of a particular node.
    """
    arguments = [('hostname', String()),
                 ('node_state', NodeStateArgument())]
    response = []


class ControlServiceLocator(CommandLocator):
    """
    Control service side of the protocol.
    """
    def __init__(self, cluster_state):
        """
        :param ClusterState cluster_state: Object that records known cluster
            state.
        """
        self.cluster_state = cluster_state

    @VersionCommand.responder
    def version(self):
        return {"major": 1, "minor": 0}

    @NodeStateCommand.responder
    def node_changed(self, hostname, node_state):
        self.cluster_state.node_changed(hostname, node_state)


class AgentLocator(CommandLocator):
    """
    Convergence agent side of the protocol.
    """
    def __init__(self, agent):
        """
        :param IConvergenceAgent agent: Convergence agent to notify of changes.
        """
        self.agent = agent

    @ClusterStatusCommand.responder
    def cluster_updated(self, configuration, state):
        self.agent.cluster_updated(configuration, state)


# In addition to the above I would need to implement IConvergenceAgent, a
# testing-oriented IConvergenceAgent implementation, and minimal
# ClusterState (the latter would be just enough to test, would be fleshed
# out in later issues).

# Might end up porting tiny bit of AMP testing infrastructure from HybridCluster too.
