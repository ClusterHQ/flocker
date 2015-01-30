# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for ``flocker.control._protocol``.
"""

from uuid import uuid4

from zope.interface import implementer

from characteristic import attributes, Attribute

from twisted.trial.unittest import SynchronousTestCase
from twisted.test.proto_helpers import StringTransport
from twisted.protocols.amp import UnknownRemoteError, RemoteAmpError
from twisted.python.failure import Failure
from twisted.internet.error import ConnectionLost
from twisted.python.filepath import FilePath

from .._protocol import (
    NodeStateArgument, DeploymentArgument, ControlServiceLocator,
    VersionCommand, ClusterStatusCommand, NodeStateCommand, IConvergenceAgent,
    build_agent_client, ControlAMPService, ControlAMP
)
from .._clusterstate import ClusterStateService
from .._model import (
    Deployment, Application, DockerImage, Node, NodeState, Manifestation,
    Dataset,
)
from .._persistence import ConfigurationPersistenceService


class LoopbackAMPClient(object):
    """
    Allow sending commands, in-memory, to an AMP command locator.
    """
    def __init__(self, command_locator):
        """
        :param command_locator: A ``CommandLocator`` instance that
            will handle commands sent using ``callRemote``.
        """
        self._locator = command_locator

    def callRemote(self, command, **kwargs):
        """
        Call the corresponding responder on the configured locator.

        @param commandType: a subclass of L{AMP_MODULE.Command}.

        @param kwargs: Keyword arguments taken by the command, a C{dict}.

        @return: A C{Deferred} that fires with the result of the responder.
        """
        arguments = command.makeArguments(kwargs, self._locator)
        responder = self._locator.locateResponder(command.commandName)
        d = responder(arguments)
        d.addCallback(command.parseResponse, self._locator)

        def massage_error(error):
            if error.check(RemoteAmpError):
                rje = error.value
                errorType = command.reverseErrors.get(
                    rje.errorCode, UnknownRemoteError)
                return Failure(errorType(rje.description))

            # In this case the actual AMP implementation closes the connection.
            # Weakly simulate that here by failing how things fail if the
            # connection closes and commands are outstanding.  This is sort of
            # terrible behavior but oh well.  https://tm.tl/7055
            return Failure(ConnectionLost())

        d.addErrback(massage_error)
        return d


APP1 = Application(
    name=u'myapp',
    image=DockerImage.from_string(u'postgresql'))
APP2 = Application(
    name=u'myapp2',
    image=DockerImage.from_string(u'mysql'))
TEST_DEPLOYMENT = Deployment(nodes=frozenset([
    Node(hostname=u'node1.example.com',
         applications=frozenset([APP1, APP2]))]))
MANIFESTATION = Manifestation(dataset=Dataset(dataset_id=unicode(uuid4())),
                              primary=True)
NODE_STATE = NodeState(running=[APP1], not_running=[APP2],
                       used_ports=[1, 2],
                       other_manifestations=frozenset([MANIFESTATION]))


class SerializationTests(SynchronousTestCase):
    """
    Tests for argument serialization.
    """
    def test_nodestate(self):
        """
        ``NodeStateArgument`` can round-trip a ``NodeState`` instance.
        """
        argument = NodeStateArgument()
        as_bytes = argument.toString(NODE_STATE)
        deserialized = argument.fromString(as_bytes)
        self.assertEqual([bytes, NODE_STATE], [type(as_bytes), deserialized])

    def test_deployment(self):
        """
        ``DeploymentArgument`` can round-trip a ``Deployment`` instance.
        """
        argument = DeploymentArgument()
        as_bytes = argument.toString(TEST_DEPLOYMENT)
        deserialized = argument.fromString(as_bytes)
        self.assertEqual([bytes, TEST_DEPLOYMENT],
                         [type(as_bytes), deserialized])


def build_control_amp_service(test):
    """
    Create a new ``ControlAMPService``.

    :param TestCase test: The test this service is for.

    :return ControlAMPService: Not started.
    """
    cluster_state = ClusterStateService()
    cluster_state.startService()
    test.addCleanup(cluster_state.stopService)
    persistence_service = ConfigurationPersistenceService(
        None, FilePath(test.mktemp()))
    persistence_service.startService()
    test.addCleanup(persistence_service.stopService)
    return ControlAMPService(cluster_state, persistence_service)


class ControlAMPTests(SynchronousTestCase):
    """
    Tests for ``ControlAMP`` and ``ControlServiceLocator``.
    """
    def setUp(self):
        self.control_amp_service = build_control_amp_service(self)
        self.protocol = ControlAMP(self.control_amp_service)
        self.client = LoopbackAMPClient(self.protocol.locator)

    def test_version(self):
        """
        ``VersionCommand`` to the control service returns the current internal
        protocol version.
        """
        self.assertEqual(
            self.successResultOf(self.client.callRemote(VersionCommand)),
            {"major": 1})

    def test_nodestate_updates_node_state(self):
        """
        ``NodeStateCommand`` updates the node state.
        """
        self.successResultOf(
            self.client.callRemote(NodeStateCommand, hostname=u"example1",
                                   node_state=NODE_STATE))
        self.assertEqual(
            self.control_amp_service.cluster_state.as_deployment(),
            Deployment(
                nodes=frozenset([
                    Node(hostname=u'example1',
                         applications=frozenset([APP1, APP2]),
                         other_manifestations=frozenset(
                             [MANIFESTATION]))])))


@implementer(IConvergenceAgent)
@attributes([Attribute("is_connected", default_value=False),
             Attribute("is_disconnected", default_value=False),
             Attribute("desired", default_value=None),
             Attribute("actual", default_value=None)])
class FakeAgent(object):
    """
    Fake agent for testing.

    Not a full verified fake since
    https://clusterhq.atlassian.net/browse/FLOC-1255 may change this a
    little.
    """
    def connected(self):
        self.is_connected = True

    def disconnected(self):
        self.is_disconnected = True

    def cluster_updated(self, configuration, cluster_state):
        self.desired = configuration
        self.actual = cluster_state


class AgentClientTests(SynchronousTestCase):
    """
    Tests for ``build_agent_client``.
    """
    def setUp(self):
        self.agent = FakeAgent()
        self.client = build_agent_client(self.agent)
        # The server needs to send commands to the client, so it acts as
        # an AMP client in that regard. Due to https://tm.tl/7761 we need
        # to access the passed in locator directly.
        self.server = LoopbackAMPClient(self.client.locator)

    def test_initially_not_connected(self):
        """
        The agent does not get told a connection was made or lost before it's
        actually happened.
        """
        self.assertEqual(self.agent, FakeAgent(is_connected=False,
                                               is_disconnected=False))

    def test_connection_made(self):
        """
        Connection made events are passed on to the agent.
        """
        self.client.makeConnection(StringTransport())
        self.assertEqual(self.agent, FakeAgent(is_connected=True))

    def test_connection_lost(self):
        """
        Connection lost events are passed on to the agent.
        """
        self.client.makeConnection(StringTransport())
        self.client.connectionLost(Failure(ConnectionLost()))
        self.assertEqual(self.agent, FakeAgent(is_connected=True,
                                               is_disconnected=True))

    def test_cluster_updated(self):
        """
        ``ClusterStatusCommand`` sent to the ``AgentClient`` result in agent
        having cluster state updated.
        """
        self.client.makeConnection(StringTransport())
        actual = Deployment(nodes=frozenset())
        d = self.server.callRemote(ClusterStatusCommand,
                                   configuration=TEST_DEPLOYMENT,
                                   state=actual)
        self.successResultOf(d)
        self.assertEqual(self.agent, FakeAgent(is_connected=True,
                                               desired=TEST_DEPLOYMENT,
                                               actual=actual))
