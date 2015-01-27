# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for ``flocker.control._protocol``.
"""

from uuid import uuid4

from twisted.trial.unittest import SynchronousTestCase
from twisted.protocols.amp import UnknownRemoteError, RemoteAmpError
from twisted.python.failure import Failure
from twisted.internet.error import ConnectionLost

from .._protocol import (
    NodeStateArgument, DeploymentArgument, ControlServiceLocator,
    VersionCommand, ClusterStatusCommand, NodeStateCommand,
)
from .._clusterstate import ClusterStateService
from .._model import (
    Deployment, Application, DockerImage, Node, NodeState, Manifestation,
    Dataset,
)


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


class ControlServiceLocatorTests(SynchronousTestCase):
    """
    Tests for ``ControlServiceLocator``.
    """
    def setUp(self):
        self.cluster_state = ClusterStateService()
        self.cluster_state.startService()
        self.addCleanup(self.cluster_state.stopService)
        self.client = LoopbackAMPClient(ControlServiceLocator(
            self.cluster_state))

    def test_version(self):
        """
        ``VersionCommand`` to the control service returns the current internal
        protocol version.
        """
        self.assertEqual(
            self.successResultOf(self.client.callRemote(VersionCommand)),
            {"major": 1})

    def test_nodestate(self):
        """
        ``NodeStateCommand`` updates the node state.
        """
        self.successResultOf(
            self.client.callRemote(NodeStateCommand, hostname=u"example1",
                                   node_state=NODE_STATE))
        self.assertEqual(self.cluster_state.as_deployment(),
                         Deployment(
                             nodes=frozenset([
                                 Node(hostname=u'example1',
                                      applications=frozenset([APP1, APP2]),
                                      other_manifestations=frozenset(
                                          [MANIFESTATION]))])))
