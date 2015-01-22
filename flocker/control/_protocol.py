"""
Communication protocol between control service and convergence agent.
"""

from twisted.protocols.amp import Argument, Command, Integer, String

from .._model import NodeState, Deployment
from .__config import current_from_configuration, marshal_configuration


class NodeStateArgument(Argument):
    """
    AMP argument that takes a ``NodeState`` object.
    """
    def fromString(self, in_bytes):
        #return json.loads(in_bytes) then decode NodeState
        pass

    def toString(self, node_state):
        #return json.dumps(marshal_configuration(node_state))
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
        #values = json.loads(in_bytes))
        #deployment_config = values["deployment"]
        #application_config = values["applications"]
        # XXX this is wrong function cause _config is terrible, but basic idea:
        #return deployment_from_configuration(deployment_config, application_config)
        pass

    def toString(self, deployment):
        # Use code in FLOC-1159 to serialize Deployment object to two JSON objects
        pass


class VersionCommand(Command):
    """
    Return configuration protocol version of the control service.

    Semantic versioning: Major version changes implies incompatibility,
    minor version implies compatible extension.
    """
    arguments = []
    response = [('major', Integer()),
                ('minor', Integer())]


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
