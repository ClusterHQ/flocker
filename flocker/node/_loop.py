"""
Convergence loop for the agent.

The convergence agent runs a loop that attempts to converge the local
state with the desired configuration as transmitted by the control
service. This involves two state machines: ClusterStatus and AgentOperation.
The ClusterStatus state machine receives inputs from the connection to the
control service, and sends inputs to the AgentOperation state machine.

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


from ._protocol import AgentClient


class AgentLoopService(Service):
    def __init__(self, host, port):
        self.agent_operation = AgentOperation()
        self.cluster_status = ClusterStatus(self.agent_operation)

    def startService(self):
        self.factory = ReconnectingClientFactory()
        self.factory.protocol = lambda: AgentClient(self)
        reactor.connectTCP(self.host, self.port)

    def stopService(self):
        # stop factory

    def connected(self, client):
        # input CONNECTED to self.agent_operation, pass reference to client in
        pass

    def disconnected(self):
        # input DISCONNECTED to self.agent_operation
        pass

    def cluster_updated(configuration, cluster_state):
        # input UPDATE with config and state to self.agent_operation
        pass


# Rich inputs for CONNECTED (AgetnClient) and UPDATE (two Deployments, desired and actual)
# Rich input for GO (AgentClient)


# AgentOperation as in state machine description above; uses AgentClient to send discovered NodeState

class AgentOperation(object):
    def __init__(self, deployer):
        # ...
