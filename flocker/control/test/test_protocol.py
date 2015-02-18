# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for ``flocker.control._protocol``.
"""

from uuid import uuid4

from zope.interface import implementer
from zope.interface.verify import verifyObject

from characteristic import attributes, Attribute

from eliot import ActionType, start_action, MemoryLogger, Logger
from eliot.testing import validate_logging, LoggedAction

from twisted.trial.unittest import SynchronousTestCase
from twisted.test.proto_helpers import StringTransport, MemoryReactor
from twisted.protocols.amp import UnknownRemoteError, RemoteAmpError, AMP
from twisted.python.failure import Failure
from twisted.internet.error import ConnectionLost
from twisted.internet.endpoints import TCP4ServerEndpoint
from twisted.internet.defer import succeed
from twisted.python.filepath import FilePath
from twisted.application.internet import StreamServerEndpointService

from .._protocol import (
    NodeStateArgument, DeploymentArgument,
    VersionCommand, ClusterStatusCommand, NodeStateCommand, IConvergenceAgent,
    AgentAMP, ControlAMPService, ControlAMP, with_eliot_context, _AgentLocator
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
            return Failure(ConnectionLost(str(error)))

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
NODE_STATE = NodeState(hostname=u'node1.example.com',
                       running=[APP1], not_running=[APP2],
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
    return ControlAMPService(cluster_state, persistence_service,
                             TCP4ServerEndpoint(MemoryReactor(), 1234))


def capturing_call_remote(capture_list, *args, **kwargs):
    # Ditch the eliot context whose context level is difficult to
    # predict.
    kwargs.pop('eliot_context')
    capture_list.append((args, kwargs))
    return succeed(None)


class ControlAMPTests(SynchronousTestCase):
    """
    Tests for ``ControlAMP`` and ``ControlServiceLocator``.
    """
    def setUp(self):
        self.control_amp_service = build_control_amp_service(self)
        self.protocol = ControlAMP(self.control_amp_service)
        self.client = LoopbackAMPClient(self.protocol.locator)

    def test_connection_made(self):
        """
        When a connection is made the ``ControlAMP`` is added to the services
        set of connections.
        """
        marker = object()
        self.control_amp_service.connections.add(marker)
        current = self.control_amp_service.connections.copy()
        self.protocol.makeConnection(StringTransport())
        self.assertEqual((current, self.control_amp_service.connections),
                         ({marker}, {marker, self.protocol}))

    def test_connection_made_send_cluster_status(self):
        """
        When a connection is made the cluster status is sent to the new client.
        """
        sent = []
        self.patch(
            self.protocol,
            "callRemote",
            lambda *args, **kwargs: capturing_call_remote(sent, *args, **kwargs)
        )
        self.control_amp_service.configuration_service.save(TEST_DEPLOYMENT)
        self.control_amp_service.cluster_state.update_node_state(NODE_STATE)

        self.protocol.makeConnection(StringTransport())
        cluster_state = self.control_amp_service.cluster_state.as_deployment()
        self.assertEqual(
            sent[0],
            (((ClusterStatusCommand,),
              dict(configuration=TEST_DEPLOYMENT,
                   state=cluster_state))))

    def test_connection_lost(self):
        """
        When a connection is lost the ``ControlAMP`` is removed from the
        service's set of connections.
        """
        marker = object()
        self.control_amp_service.connections.add(marker)
        self.patch(self.protocol, "callRemote",
                   lambda *args, **kwargs: succeed(None))
        self.protocol.makeConnection(StringTransport())
        self.protocol.connectionLost(Failure(ConnectionLost()))
        self.assertEqual(self.control_amp_service.connections, {marker})

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
            self.client.callRemote(NodeStateCommand,
                                   node_state=NODE_STATE,
                                   eliot_context=TEST_ACTION_ID))
        self.assertEqual(
            self.control_amp_service.cluster_state.as_deployment(),
            Deployment(
                nodes=frozenset([
                    Node(hostname=u'node1.example.com',
                         applications=frozenset([APP1, APP2]),
                         other_manifestations=frozenset(
                             [MANIFESTATION]))])))

    def test_nodestate_notifies_all_connected(self):
        """
        ``NodeStateCommand`` results in all connected ``ControlAMP``
        connections getting the updated cluster state along with the
        desired configuration.
        """
        self.control_amp_service.configuration_service.save(TEST_DEPLOYMENT)
        self.protocol.makeConnection(StringTransport())
        another_protocol = ControlAMP(self.control_amp_service)
        another_protocol.makeConnection(StringTransport())
        sent1 = []
        sent2 = []

        self.patch(
            self.protocol,
            "callRemote",
            lambda *args, **kwargs: capturing_call_remote(sent1, *args, **kwargs)
        )
        self.patch(
            another_protocol,
            "callRemote",
            lambda *args, **kwargs: capturing_call_remote(sent2, *args, **kwargs)
        )

        self.successResultOf(
            self.client.callRemote(NodeStateCommand,
                                   node_state=NODE_STATE,
                                   eliot_context=TEST_ACTION_ID))
        cluster_state = self.control_amp_service.cluster_state.as_deployment()
        self.assertListEqual(
            [sent1[-1], sent2[-1]],
            [(((ClusterStatusCommand,),
              dict(configuration=TEST_DEPLOYMENT,
                   state=cluster_state)))] * 2)


class ControlAMPServiceTests(SynchronousTestCase):
    """
    Unit tests for ``ControlAMPService``.
    """
    def test_start_service(self):
        """
        Starting the service listens with a factory that creates
        ``ControlAMP`` instances pointing at the service.
        """
        service = build_control_amp_service(self)
        initial = service.endpoint_service.running
        service.startService()
        protocol = service.endpoint_service.factory.buildProtocol(None)
        self.assertEqual(
            (initial, service.endpoint_service.running,
             service.endpoint_service.__class__,
             protocol.__class__, protocol.control_amp_service),
            (False, True, StreamServerEndpointService, ControlAMP, service))

    def test_stop_service_endpoint(self):
        """
        Stopping the service stops listening on the endpoint.
        """
        service = build_control_amp_service(self)
        service.startService()
        service.stopService()
        self.assertEqual(service.endpoint_service.running, False)

    def test_stop_service_connections(self):
        """
        Stopping the service closes all connections.
        """
        service = build_control_amp_service(self)
        service.startService()
        connections = [ControlAMP(service) for i in range(3)]
        initial_disconnecting = []
        for c in connections:
            c.makeConnection(StringTransport())
            initial_disconnecting.append(c.transport.disconnecting)
        service.stopService()
        self.assertEqual(
            (initial_disconnecting,
             [c.transport.disconnecting for c in connections]),
            ([False] * 3, [True] * 3))

    def assertDictEqual(self, expected, actual):
        """
        """
        actual = actual.copy()
        for expected_key, expected_value in expected.items():
            actual_value = actual.pop(expected_key)
            self.assertEqual(
                expected_value, actual_value,
                'Non-equal dictionary value. '
                'Key: {!r} Expected: {!r} Actual: {!r}'.format(
                    expected_key, expected_value, actual_value)
            )
        self.assertEqual({}, actual)

    def assertArgsEqual(self, expected, actual):
        expected_args, expected_kwargs = expected
        actual_args, actual_kwargs = actual

        self.assertEqual(expected_args, actual_args)
        self.assertDictEqual(expected_kwargs, actual_kwargs)

    def test_configuration_change(self):
        """
        A configuration change results in connected protocols being notified
        of new cluster status.
        """
        service = build_control_amp_service(self)
        service.startService()
        protocol = ControlAMP(service)
        protocol.makeConnection(StringTransport())
        sent = []
        self.patch(
            protocol,
            "callRemote",
            lambda *args, **kwargs: capturing_call_remote(sent, *args, **kwargs)
        )

        service.configuration_service.save(TEST_DEPLOYMENT)
        # Should only be one callRemote call.
        (sent,) = sent
        self.assertArgsEqual(
            sent,
            (
                (ClusterStatusCommand,),
                dict(configuration=TEST_DEPLOYMENT,
                     state=Deployment(nodes=frozenset())
                )
            )
        )


@implementer(IConvergenceAgent)
@attributes([Attribute("is_connected", default_value=False),
             Attribute("is_disconnected", default_value=False),
             Attribute("desired", default_value=None),
             Attribute("actual", default_value=None),
             Attribute("client", default_value=None)])
class FakeAgent(object):
    """
    Fake agent for testing.
    """
    logger = Logger()
    def connected(self, client):
        self.is_connected = True
        self.client = client

    def disconnected(self):
        self.is_disconnected = True
        self.client = None

    def cluster_updated(self, configuration, cluster_state):
        self.desired = configuration
        self.actual = cluster_state


TEST_ACTION = start_action(MemoryLogger(), 'test:action')
TEST_ACTION_ID = TEST_ACTION.serialize_task_id()

class AgentClientTests(SynchronousTestCase):
    """
    Tests for ``AgentAMP``.
    """
    def setUp(self):
        self.agent = FakeAgent()
        self.client = AgentAMP(self.agent)
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
        self.assertEqual(self.agent, FakeAgent(is_connected=True,
                                               client=self.client))

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
        d = self.server.callRemote(
            ClusterStatusCommand,
            configuration=TEST_DEPLOYMENT,
            state=actual,
            eliot_context=TEST_ACTION_ID
        )

        self.successResultOf(d)
        self.assertEqual(self.agent, FakeAgent(is_connected=True,
                                               client=self.client,
                                               desired=TEST_DEPLOYMENT,
                                               actual=actual))


def iconvergence_agent_tests_factory(fixture):
    """
    Create tests that verify basic ``IConvergenceAgent`` compliance.

    :param fixture: Callable that takes ``SynchronousTestCase`` instance
        and returns a ``IConvergenceAgent`` provider.

    :return: ``SynchronousTestCase`` subclass.
    """
    class IConvergenceAgentTests(SynchronousTestCase):
        """
        Tests for ``IConvergenceAgent``.
        """
        def test_connected(self):
            """
            ``IConvergenceAgent.connected()`` takes an AMP instance.
            """
            agent = fixture(self)
            agent.connected(AMP())

        def test_disconnected(self):
            """
            ``IConvergenceAgent.disconnected()`` can be called after
            ``IConvergenceAgent.connected()``.
            """
            agent = fixture(self)
            agent.connected(AMP())
            agent.disconnected()

        def test_reconnected(self):
            """
            ``IConvergenceAgent.connected()`` can be called after
            ``IConvergenceAgent.disconnected()``.
            """
            agent = fixture(self)
            agent.connected(AMP())
            agent.disconnected()
            agent.connected(AMP())

        def test_cluster_updated(self):
            """
            ``IConvergenceAgent.cluster_updated()`` takes two ``Deployment``
            instances.
            """
            agent = fixture(self)
            agent.connected(AMP())
            agent.cluster_updated(
                Deployment(nodes=frozenset()), Deployment(nodes=frozenset()))

        def test_interface(self):
            """
            The object provides ``IConvergenceAgent``.
            """
            agent = fixture(self)
            self.assertTrue(verifyObject(IConvergenceAgent, agent))

    return IConvergenceAgentTests


class FakeAgentInterfaceTests(iconvergence_agent_tests_factory(
        lambda test: FakeAgent())):
    """
    ``IConvergenceAgent`` tests for ``FakeAgent``.
    """

SEND_REQUEST = ActionType(
    u'test:send_request',
    [],
    [],
    u'client makes request to server.'
)

HANDLE_REQUEST = ActionType(
    u'test:handle_request',
    [],
    [],
    u'server receives request from client.'
)


class ClientProcess(object):
    logger = None

    def send_request(self, server, **kwargs):
        """
        Send request.
        """
        with SEND_REQUEST(self.logger) as action:
            return server.handle_request(
                eliot_context=action.serialize_task_id(),
                **kwargs
            )


class ServerProcess(object):
    logger = None

    @with_eliot_context
    def handle_request(self, arg1, arg2):
        """
        Handle request.
        """
        with HANDLE_REQUEST(self.logger):
            return dict(arg1=arg1, arg2=arg2)


class WithEliotContextTests(SynchronousTestCase):
    """
    Tests for ``with_eliot_context``.
    """
    def assert_child_action(self, logger):
        """
        The Client sets the logging context which means that Server Actions
        appear as children of the Client Action.
        """
        # There should only be one...
        (client_action,) = LoggedAction.of_type(logger.messages, SEND_REQUEST)
        (server_action,) = LoggedAction.of_type(
            logger.messages, HANDLE_REQUEST)
        for child_action in client_action.descendants():
            if child_action == server_action:
                break
        else:
            self.fail(
                'Child action not found. Expected: {!r} in {!r}'.format(
                    server_action, list(client_action.descendants()))
            )

    @validate_logging(assert_child_action)
    def test_decorated_called(self, logger):
        """
        The decorator returned by ``with_eliot_context`` calls the decorated
        function with the keyword arguments supplied to it and returns its
        return value.
        """
        client = ClientProcess()
        client.logger = logger

        server = ServerProcess()
        server.logger = logger

        expected_results = dict(
            arg1=object(),
            arg2=object()
        )
        actual_result = client.send_request(server, **expected_results)

        self.assertEqual(expected_results, actual_result)

    def test_decorated_name(self):
        """
        ``with_eliot_context`` returns a decorator function with the same name
        as the decorated function.
        """
        self.assertEqual(
            'handle_request',
            ServerProcess().handle_request.__name__
        )

    def test_decorated_docstring(self):
        """
        ``with_eliot_context`` returns a decorator function with the same
        docstring as the decorated function.
        """
        self.assertEqual(
            'Handle request.',
            ServerProcess().handle_request.__doc__.strip()
        )

    def test_positional_arguments_error(self):
        """
        The decorator returned by ``with_eliot_context`` does not accept
        positional arguments, regardless of whether the decorated function
        accepts them.
        """
        server = ServerProcess()
        dummy_eliot_context = object()
        error = self.assertRaises(
            TypeError,
            server.handle_request, dummy_eliot_context, 'arg1', 'arg2'
        )
        self.assertEqual(
            'responder() takes exactly 2 arguments (4 given)',
            str(error)
        )

class ClusterStatusCommandTests(SynchronousTestCase):
    """
    Tests for ``ClusterStatusCommand``.
    """
    def test_command_arguments(self):
        """
        ClusterStatusCommand requires the following arguments.
        """
        self.assertEqual(
            sorted(['configuration', 'state', 'eliot_context']),
            sorted(v[0] for v in ClusterStatusCommand.arguments))


class AgentLocatorTests(SynchronousTestCase):
    """
    Tests for ``_AgentLocator``.
    """
    @validate_logging(None)
    def test_logger(self, logger):
        """
        ``_AgentLocator.logger`` is a property that returns the ``logger``
        attribute of the ``Agent`` supplied to its initialiser.
        """
        fake_agent = FakeAgent()
        fake_agent.logger = logger
        locator = _AgentLocator(agent=fake_agent)
        self.assertIs(logger, locator.logger)


class ClusterUpdatedTests(SynchronousTestCase):
    """
    Tests for the responder for ``ClusterStatusCommand``.
    """
    @validate_logging(None)
    def test_responder_logging(self, logger):
        """
        ``cluster_updated`` is decorated using ``with_eliot_context`` and
        therefore requires an eliot_context argument. The supplied
        eliot_context is used as the context for messages logged in that
        method.
        """
        fake_agent = FakeAgent()
        fake_agent.logger = logger
        locator = _AgentLocator(agent=fake_agent)
        with SEND_REQUEST(logger) as action:
            locator.cluster_updated(
                eliot_context=action.serialize_task_id(),
                configuration=object(),
                state=object()
            )
        (test_action,) = LoggedAction.of_type(logger.messages, SEND_REQUEST)
        (child_action,) = test_action.children

        self.assertEqual(
            u'eliot:remote_task',
            child_action.start_message['action_type']
        )
