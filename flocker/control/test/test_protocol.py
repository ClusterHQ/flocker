# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for ``flocker.control._protocol``.
"""

from uuid import uuid4

from zope.interface import implementer
from zope.interface.verify import verifyObject

from characteristic import attributes, Attribute

from eliot import ActionType, start_action, MemoryLogger, Logger
from eliot.testing import validate_logging, assertHasAction, LoggedAction

from twisted.internet.error import ConnectionDone
from twisted.test.iosim import connectedServerAndClient
from twisted.trial.unittest import SynchronousTestCase
from twisted.test.proto_helpers import StringTransport, MemoryReactor
from twisted.protocols.amp import (
    UnknownRemoteError, RemoteAmpError, CommandLocator, AMP,
)
from twisted.python.failure import Failure
from twisted.internet.error import ConnectionLost
from twisted.internet.endpoints import TCP4ServerEndpoint
from twisted.internet.defer import succeed, fail
from twisted.python.filepath import FilePath
from twisted.application.internet import StreamServerEndpointService
from twisted.internet.ssl import ClientContextFactory
from twisted.internet.task import Clock

from .._protocol import (
    PING_INTERVAL, SerializableArgument,
    VersionCommand, ClusterStatusCommand, NodeStateCommand, IConvergenceAgent,
    NoOp, AgentAMP, ControlAMPService, ControlAMP, _AgentLocator,
    ControlServiceLocator, LOG_SEND_CLUSTER_STATE, LOG_SEND_TO_AGENT,
)
from .._model import ChangeSource
from .._clusterstate import ClusterStateService
from .. import (
    Deployment, Application, DockerImage, Node, NodeState, Manifestation,
    Dataset, DeploymentState, NonManifestDatasets,
)
from .._persistence import ConfigurationPersistenceService
from .clusterstatetools import advance_some, advance_rest


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
    image=DockerImage.from_string(u'mysql'),
    running=False)
TEST_DEPLOYMENT = Deployment(nodes=frozenset([
    Node(hostname=u'node1.example.com',
         applications=frozenset([APP1, APP2]))]))
MANIFESTATION = Manifestation(dataset=Dataset(dataset_id=unicode(uuid4())),
                              primary=True)

# A very simple piece of node state that makes for nice-looking, easily-read
# test failures.  It arbitrarily supplies only ports because integers have a
# very simple representation.
SIMPLE_NODE_STATE = NodeState(
    hostname=u"192.0.2.17", uuid=uuid4(), applications=[], used_ports=[1],
)

NODE_STATE = NodeState(hostname=u'node1.example.com',
                       applications=[APP1, APP2],
                       used_ports=[1, 2],
                       devices={}, paths={},
                       manifestations={MANIFESTATION.dataset_id:
                                       MANIFESTATION})

dataset = Dataset(dataset_id=unicode(uuid4()))
NONMANIFEST = NonManifestDatasets(
    datasets={dataset.dataset_id: dataset}
)
del dataset


class SerializationTests(SynchronousTestCase):
    """
    Tests for argument serialization.
    """
    def test_nodestate(self):
        """
        ``SerializableArgument`` can round-trip a ``NodeState`` instance.
        """
        argument = SerializableArgument(NodeState)
        as_bytes = argument.toString(NODE_STATE)
        deserialized = argument.fromString(as_bytes)
        self.assertEqual([bytes, NODE_STATE],
                         [type(as_bytes), deserialized])

    def test_deployment(self):
        """
        ``SerializableArgument`` can round-trip a ``Deployment`` instance.
        """
        argument = SerializableArgument(Deployment)
        as_bytes = argument.toString(TEST_DEPLOYMENT)
        deserialized = argument.fromString(as_bytes)
        self.assertEqual([bytes, TEST_DEPLOYMENT],
                         [type(as_bytes), deserialized])

    def test_nonmanifestdatasets(self):
        """
        ``SerializableArgument`` can round-trip a ``NonManifestDatasets``
        instance.
        """
        argument = SerializableArgument(NonManifestDatasets)
        as_bytes = argument.toString(NONMANIFEST)
        deserialized = argument.fromString(as_bytes)
        self.assertEqual(
            [bytes, NONMANIFEST],
            [type(as_bytes), deserialized],
        )

    def test_multiple_type_serialization(self):
        """
        ``SerializableArgument`` can be given multiple types to allow instances
        of any of those types to be serialized and deserialized.
        """
        argument = SerializableArgument(list, dict)
        objects = [
            [u"foo"],
            {u"bar": u"baz"},
        ]
        serialized = list(
            argument.toString(o)
            for o in objects
        )
        unserialized = list(
            argument.fromString(s)
            for s in serialized
        )
        self.assertEqual(objects, unserialized)

    def test_wrong_type_serialization(self):
        """
        ``SerializableArgument`` throws a ``TypeError`` if one attempts to
        serialize an object of the wrong type.
        """
        argument = SerializableArgument(Deployment)
        self.assertRaises(TypeError, argument.toString, NODE_STATE)

    def test_wrong_type_deserialization(self):
        """
        ``SerializableArgument`` throws a ``TypeError`` if one attempts to
        deserialize an object of the wrong type.
        """
        argument = SerializableArgument(Deployment)
        as_bytes = argument.toString(TEST_DEPLOYMENT)
        self.assertRaises(
            TypeError, SerializableArgument(NodeState).fromString, as_bytes)


def build_control_amp_service(test, reactor=None):
    """
    Create a new ``ControlAMPService``.

    :param TestCase test: The test this service is for.

    :return ControlAMPService: Not started.
    """
    if reactor is None:
        reactor = Clock()
    cluster_state = ClusterStateService(reactor)
    cluster_state.startService()
    test.addCleanup(cluster_state.stopService)
    persistence_service = ConfigurationPersistenceService(
        None, FilePath(test.mktemp()))
    persistence_service.startService()
    test.addCleanup(persistence_service.stopService)
    return ControlAMPService(reactor, cluster_state, persistence_service,
                             TCP4ServerEndpoint(MemoryReactor(), 1234),
                             # Easiest TLS context factory to create:
                             ClientContextFactory())


class ControlTestCase(SynchronousTestCase):
    """
    Base TestCase for control tests that supplies a utility
    method to patch the callRemote method of the AMP protocol instance,
    discarding Eliot contexts whose context level may be unknown.
    """

    def patch_call_remote(self, capture_list, protocol):
        """
        Patch the callRemote method for this test case's protocol.

        :param capture_list: A `list` to which results will be added.

        :param protocol: Either `None` to default to self.protocol, or
            a ``ControlAMP`` instance.
        """

        def capture_call_remote(capture, *args, **kwargs):
            # Ditch the eliot context whose context level is difficult to
            # predict.
            kwargs.pop('eliot_context')
            capture.append((args, kwargs))
            return succeed(None)

        # Patching is bad.
        # https://clusterhq.atlassian.net/browse/FLOC-1603
        self.patch(
            protocol,
            "callRemote",
            lambda *args, **kwargs: capture_call_remote(
                capture_list, *args, **kwargs)
        )


class ControlAMPTests(ControlTestCase):
    """
    Tests for ``ControlAMP`` and ``ControlServiceLocator``.
    """
    def setUp(self):
        self.reactor = Clock()
        self.control_amp_service = build_control_amp_service(
            self, self.reactor,
        )
        self.protocol = ControlAMP(self.reactor, self.control_amp_service)
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
        self.patch_call_remote(sent, self.protocol)
        self.control_amp_service.configuration_service.save(TEST_DEPLOYMENT)
        self.control_amp_service.cluster_state.apply_changes([NODE_STATE])

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
        # Patching is bad.
        # https://clusterhq.atlassian.net/browse/FLOC-1603
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
        changes = (NODE_STATE, NONMANIFEST)
        self.successResultOf(
            self.client.callRemote(NodeStateCommand,
                                   state_changes=changes,
                                   eliot_context=TEST_ACTION))
        self.assertEqual(
            DeploymentState(
                nodes={NODE_STATE},
                nonmanifest_datasets=NONMANIFEST.datasets,
            ),
            self.control_amp_service.cluster_state.as_deployment(),
        )

    def test_activity_refreshes_node_state(self):
        """
        Any time commands are dispatched by ``ControlAMP`` its activity
        timestamp is refreshed to prevent previously applied state from
        expiring.
        """
        cluster_state = self.control_amp_service.cluster_state

        # Deliver some initial state (T1) which can be expected to be
        # preserved.
        self.successResultOf(
            self.client.callRemote(
                NodeStateCommand,
                state_changes=(SIMPLE_NODE_STATE,),
                eliot_context=TEST_ACTION,
            )
        )
        # Let a little time pass (T2) and then cause some activity.
        advance_some(self.reactor)
        self.client.callRemote(NoOp)

        # Let enough time pass (T3) to reach EXPIRATION_TIME from T1
        advance_rest(self.reactor)
        before_wipe_state = cluster_state.as_deployment()

        # Let enough time pass (T4) to reach EXPIRATION_TIME from T2
        advance_some(self.reactor)
        after_wipe_state = cluster_state.as_deployment()

        # The state from T1 should not have been wiped at T3 but it should have
        # been wiped at T4.
        self.assertEqual(
            (before_wipe_state, after_wipe_state),
            (DeploymentState(nodes={SIMPLE_NODE_STATE}), DeploymentState()),
        )

    def test_nodestate_notifies_all_connected(self):
        """
        ``NodeStateCommand`` results in all connected ``ControlAMP``
        connections getting the updated cluster state along with the
        desired configuration.
        """
        self.control_amp_service.configuration_service.save(TEST_DEPLOYMENT)
        self.protocol.makeConnection(StringTransport())
        another_protocol = ControlAMP(self.reactor, self.control_amp_service)
        another_protocol.makeConnection(StringTransport())
        sent1 = []
        sent2 = []

        self.patch_call_remote(sent1, self.protocol)
        self.patch_call_remote(sent2, protocol=another_protocol)

        self.successResultOf(
            self.client.callRemote(NodeStateCommand,
                                   state_changes=(NODE_STATE,),
                                   eliot_context=TEST_ACTION))
        cluster_state = self.control_amp_service.cluster_state.as_deployment()
        self.assertListEqual(
            [sent1[-1], sent2[-1]],
            [(((ClusterStatusCommand,),
              dict(configuration=TEST_DEPLOYMENT,
                   state=cluster_state)))] * 2)


class ControlAMPServiceTests(ControlTestCase):
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
        control_factory = service.endpoint_service.factory.wrappedFactory
        protocol = control_factory.buildProtocol(None)
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
        connections = [ControlAMP(Clock(), service) for i in range(3)]
        initial_disconnecting = []
        for c in connections:
            c.makeConnection(StringTransport())
            initial_disconnecting.append(c.transport.disconnecting)
        service.stopService()
        self.assertEqual(
            (initial_disconnecting,
             [c.transport.disconnecting for c in connections]),
            ([False] * 3, [True] * 3))

    def assertArgsEqual(self, expected, actual):
        """
        Utility method to assert that two sets of arguments are equal.
        This method takes two tuples that are unpacked in to a list (args)
        and a dictionary (kwargs) and performs separate comparisons of these
        between the supplied expected and actual parameters.

        :param expected: A `tuple` of the expected args and kwargs.
        :param actual: A `tuple` of the actual args and kwargs.
        """
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
        protocol = ControlAMP(Clock(), service)
        protocol.makeConnection(StringTransport())
        sent = []
        self.patch_call_remote(sent, protocol=protocol)

        service.configuration_service.save(TEST_DEPLOYMENT)
        # Should only be one callRemote call.
        (sent,) = sent
        self.assertArgsEqual(
            sent,
            (
                (ClusterStatusCommand,),
                dict(
                    configuration=TEST_DEPLOYMENT,
                    state=DeploymentState(),
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


class AgentClientTests(SynchronousTestCase):
    """
    Tests for ``AgentAMP``.
    """
    def setUp(self):
        self.agent = FakeAgent()
        self.client = AgentAMP(Clock(), self.agent)
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
        actual = DeploymentState(nodes=[])
        d = self.server.callRemote(
            ClusterStatusCommand,
            configuration=TEST_DEPLOYMENT,
            state=actual,
            eliot_context=TEST_ACTION
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


class ClusterStatusCommandTests(SynchronousTestCase):
    """
    Tests for ``ClusterStatusCommand``.
    """
    def test_command_arguments(self):
        """
        ClusterStatusCommand requires the following arguments.
        """
        self.assertItemsEqual(
            ['configuration', 'state', 'eliot_context'],
            (v[0] for v in ClusterStatusCommand.arguments))


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
        self.patch(fake_agent, 'logger', logger)
        locator = _AgentLocator(agent=fake_agent)
        self.assertIs(logger, locator.logger)


class ControlServiceLocatorTests(SynchronousTestCase):
    """
    Tests for ``ControlServiceLocator``.
    """
    @validate_logging(None)
    def test_logger(self, logger):
        """
        ``ControlServiceLocator.logger`` is a property that returns the
        ``logger`` attribute of the ``ControlAMPService`` supplied to its
        initialiser.
        """
        fake_control_amp_service = build_control_amp_service(self)
        self.patch(fake_control_amp_service, 'logger', logger)
        locator = ControlServiceLocator(
            reactor=Clock(),
            control_amp_service=fake_control_amp_service
        )
        self.assertIs(logger, locator.logger)


class SendStateToConnectionsTests(SynchronousTestCase):
    """
    Tests for ``ControlAMPService._send_state_to_connections``.
    """
    @validate_logging(None)
    def test_logging(self, logger):
        """
        ``_send_state_to_connections`` logs a single LOG_SEND_CLUSTER_STATE
        action and a LOG_SEND_TO_AGENT action for the remote calls to each of
        its connections.
        """
        control_amp_service = build_control_amp_service(self)
        self.patch(control_amp_service, 'logger', logger)

        connection_protocol = ControlAMP(Clock(), control_amp_service)
        # Patching is bad.
        # https://clusterhq.atlassian.net/browse/FLOC-1603
        connection_protocol.callRemote = lambda *args, **kwargs: succeed({})

        control_amp_service._send_state_to_connections(
            connections=[connection_protocol])

        assertHasAction(
            self,
            logger,
            LOG_SEND_CLUSTER_STATE,
            succeeded=True,
            startFields={
                "configuration": (
                    control_amp_service.configuration_service.get()
                ),
                "state": control_amp_service.cluster_state.as_deployment()
            }
        )

        assertHasAction(
            self,
            logger,
            LOG_SEND_TO_AGENT,
            succeeded=True,
            startFields={
                "agent": connection_protocol,
            }
        )

    @validate_logging(None)
    def test_error_sending(self, logger):
        """
        An error sending to one agent does not prevent others from being
        notified.
        """
        control_amp_service = build_control_amp_service(self)
        self.patch(control_amp_service, 'logger', logger)

        connected_protocol = ControlAMP(Clock(), control_amp_service)
        # Patching is bad.
        # https://clusterhq.atlassian.net/browse/FLOC-1603
        connected_protocol.callRemote = lambda *args, **kwargs: succeed({})

        error = ConnectionLost()
        disconnected_protocol = ControlAMP(Clock(), control_amp_service)
        results = [succeed({}), fail(error)]
        # Patching is bad.
        # https://clusterhq.atlassian.net/browse/FLOC-1603
        disconnected_protocol.callRemote = (
            lambda *args, **kwargs: results.pop(0))

        control_amp_service.connected(disconnected_protocol)
        control_amp_service.connected(connected_protocol)
        control_amp_service.node_changed(
            ChangeSource(),
            (NodeState(hostname=u"1.2.3.4"),)
        )

        actions = LoggedAction.ofType(logger.messages, LOG_SEND_TO_AGENT)
        self.assertEqual(
            [action.end_message["exception"] for action in actions
             if not action.succeeded],
            [u"twisted.internet.error.ConnectionLost"])


class _NoOpCounter(CommandLocator):
    noops = 0

    @NoOp.responder
    def noop(self):
        self.noops += 1
        return {}


class PingTestsMixin(object):
    """
    Mixin for ``TestCase`` defining tests for an ``AMP`` protocol that
    periodically sends no-op ping messages.
    """
    def test_periodic_noops(self):
        """
        When connected, the protocol sends ``NoOp`` commands at a fixed
        interval.
        """
        expected_pings = 3
        reactor = Clock()
        locator = _NoOpCounter()
        peer = AMP(locator=locator)
        protocol = self.build_protocol(reactor)
        pump = connectedServerAndClient(lambda: protocol, lambda: peer)[2]
        for i in range(expected_pings):
            reactor.advance(PING_INTERVAL.total_seconds())
            pump.flush()
        self.assertEqual(locator.noops, expected_pings)

    def test_stop_pinging_on_connection_lost(self):
        """
        When the protocol loses its connection, it stops trying to send
        ``NoOp`` commands.
        """
        reactor = Clock()
        protocol = self.build_protocol(reactor)
        transport = StringTransport()
        protocol.makeConnection(transport)
        transport.clear()
        protocol.connectionLost(Failure(ConnectionDone("test, simulated")))
        reactor.advance(PING_INTERVAL.total_seconds())
        self.assertEqual(b"", transport.value())


class ControlAMPPingTests(SynchronousTestCase, PingTestsMixin):
    """
    Tests for pinging done by ``ControlAMP``.
    """
    def build_protocol(self, reactor):
        control_amp_service = build_control_amp_service(
            self, reactor,
        )
        return ControlAMP(reactor, control_amp_service)


class AgentAMPPingTests(SynchronousTestCase, PingTestsMixin):
    """
    Tests for pinging done by ``AgentAMP``.
    """
    def build_protocol(self, reactor):
        return AgentAMP(reactor, FakeAgent())
