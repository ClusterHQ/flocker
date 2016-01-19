# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for ``flocker.control._protocol``.
"""

from uuid import uuid4
from json import loads

from zope.interface import implementer
from zope.interface.verify import verifyObject

from characteristic import attributes, Attribute

from eliot import ActionType, start_action, MemoryLogger, Logger
from eliot.testing import (
    capture_logging, validate_logging, assertHasAction,
)

from twisted.internet.error import ConnectionDone
from twisted.test.iosim import connectedServerAndClient
from twisted.test.proto_helpers import StringTransport, MemoryReactor
from twisted.protocols.amp import (
    MAX_VALUE_LENGTH, IArgumentType, Command, String, ListOf, Integer,
    UnknownRemoteError, RemoteAmpError, CommandLocator, AMP, parseString,
)
from twisted.python.failure import Failure
from twisted.internet.error import ConnectionLost
from twisted.internet.endpoints import TCP4ServerEndpoint
from twisted.internet.defer import succeed
from twisted.python.filepath import FilePath
from twisted.application.internet import StreamServerEndpointService
from twisted.internet.ssl import ClientContextFactory
from twisted.internet.task import Clock

from ...testtools import TestCase
from ...testtools.amp import DelayedAMPClient, connected_amp_protocol

from .._protocol import (
    PING_INTERVAL, Big, SerializableArgument,
    VersionCommand, ClusterStatusCommand, NodeStateCommand, IConvergenceAgent,
    NoOp, AgentAMP, ControlAMPService, ControlAMP, _AgentLocator,
    ControlServiceLocator, LOG_SEND_CLUSTER_STATE, LOG_SEND_TO_AGENT,
    AGENT_CONNECTED, caching_wire_encode, SetNodeEraCommand,
    timeout_for_protocol,
)
from .._clusterstate import ClusterStateService
from .. import (
    Deployment, Application, DockerImage, Node, NodeState, Manifestation,
    Dataset, DeploymentState, NonManifestDatasets,
)
from .._persistence import ConfigurationPersistenceService, wire_encode
from .clusterstatetools import advance_some, advance_rest


def arbitrary_transformation(deployment):
    """
    Make some change to a deployment configuration.  Any change.

    The exact change made is unspecified but the resulting ``Deployment`` will
    be different from the given ``Deployment``.

    :param Deployment deployment: A configuration to change.

    :return: A ``Deployment`` similar but not exactly equal to the given.
    """
    return deployment.transform(
        ["nodes"],
        lambda nodes: nodes.add(Node(uuid=uuid4())),
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
        self.transport = StringTransportWithAbort()

    def callRemote(self, command, **kwargs):
        """
        Call the corresponding responder on the configured locator.

        @param commandType: a subclass of L{AMP_MODULE.Command}.

        @param kwargs: Keyword arguments taken by the command, a C{dict}.

        @return: A C{Deferred} that fires with the result of the responder.
        """
        # Get a Box for the supplied arguments. E.g.
        # command = ClusterStatusUpdate
        # kwargs = {"configuration": Deployment(nodes={Node(...)})}
        # The Box contains the Deployment object converted to nested dict. E.g.
        # Box({"configuration": {"$__class__$": "Deployment", ...}})
        argument_box = command.makeArguments(kwargs, self._locator)

        # Serialize the arguments to prove that we can.  For example, if an
        # argument would serialize to more than 64kB then we can't actually
        # serialize it so we want a test attempting this to fail.
        # Wire format will contain bytes. E.g.
        # b"\x12\x32configuration..."
        wire_format = argument_box.serialize()

        # Now decode the bytes back to a Box
        [decoded_argument_box] = parseString(wire_format)

        # And supply that to the responder which internally reverses
        # makeArguments -> back to kwargs
        responder = self._locator.locateResponder(command.commandName)
        d = responder(decoded_argument_box)

        def serialize_response(response_box):
            # As above, prove we can serialize the response.
            wire_format = response_box.serialize()
            [decoded_response_box] = parseString(wire_format)
            return decoded_response_box

        d.addCallback(serialize_response)
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

# 800 is arbitrarily selected.  The two interesting properties it has are:
#
#   * It is large enough that serializing the result exceeds the native AMP
#     size limit.
#   * As of September 2015 it is the target for Flocker "scaling".
#
_MANY_CONTAINERS = 800


def huge_node(node_prototype):
    """
    Return a node with many applications.

    :param node_prototype: A ``Node`` or ``NodeState`` to use as a template for
        the resulting node.

    :return: An object like ``node_prototype`` but with its applications
        replaced by a large collection of applications.
    """
    image = DockerImage.from_string(u'postgresql')
    applications = [
        Application(name=u'postgres-{}'.format(i), image=image)
        for i in range(_MANY_CONTAINERS)
    ]
    return node_prototype.set(applications=applications)


def _huge(deployment_prototype, node_prototype):
    """
    Return a deployment with many applications.

    :param deployment_prototype: A ``Deployment`` or ``DeploymentState`` to use
        as a template for the resulting deployment.
    :param node_prototype: See ``huge_node``.

    :return: An object like ``deployment_prototype`` but with a node like
        ``node_prototype`` added (or modified) so as to include a large number
        of applications.
    """
    return deployment_prototype.update_node(
        huge_node(node_prototype),
    )


def huge_deployment():
    """
    Return a configuration with many containers.

    :rtype: ``Deployment``
    """
    return _huge(Deployment(), Node(hostname=u'192.0.2.31'))


def huge_state():
    """
    Return a state with many containers.

    :rtype: ``DeploymentState``
    """
    return _huge(
        DeploymentState(),
        NodeState(hostname=u'192.0.2.31', applications=[]),
    )


# A very simple piece of node state that makes for nice-looking, easily-read
# test failures.  It arbitrarily supplies only ports because integers have a
# very simple representation.
SIMPLE_NODE_STATE = NodeState(
    hostname=u"192.0.2.17", uuid=uuid4(), applications=[],
)

NODE_STATE = NodeState(hostname=u'node1.example.com',
                       applications=[APP1, APP2],
                       devices={}, paths={},
                       manifestations={MANIFESTATION.dataset_id:
                                       MANIFESTATION})

dataset = Dataset(dataset_id=unicode(uuid4()))
NONMANIFEST = NonManifestDatasets(
    datasets={dataset.dataset_id: dataset}
)
del dataset


class BigArgumentTests(TestCase):
    """
    Tests for ``Big``.
    """
    class CommandWithBigArgument(Command):
        arguments = [
            ("big", Big(String())),
        ]

    class CommandWithTwoBigArgument(Command):
        arguments = [
            ("big", Big(String())),
            ("large", Big(String())),
        ]

    class CommandWithBigAndRegularArgument(Command):
        arguments = [
            ("big", Big(String())),
            ("regular", String()),
        ]

    class CommandWithBigListArgument(Command):
        arguments = [
            ("big", Big(ListOf(Integer()))),
        ]

    def test_interface(self):
        """
        ``Big`` instances provide ``IArgumentType``.
        """
        big = dict(self.CommandWithBigArgument.arguments)["big"]
        self.assertTrue(verifyObject(IArgumentType, big))

    def assert_roundtrips(self, command, **kwargs):
        """
        ``kwargs`` supplied to ``command`` can be serialized and unserialized.
        """
        amp_protocol = None
        argument_box = command.makeArguments(kwargs, amp_protocol)
        [roundtripped] = parseString(argument_box.serialize())
        parsed_objects = command.parseArguments(roundtripped, amp_protocol)
        self.assertEqual(kwargs, parsed_objects)

    def test_roundtrip_non_string(self):
        """
        When ``Big`` wraps a non-string argument, it can serialize and
        unserialize it.
        """
        some_list = range(10)
        self.assert_roundtrips(self.CommandWithBigListArgument, big=some_list)

    def test_roundtrip_small(self):
        """
        ``Big`` can serialize and unserialize argmuments which are smaller then
        MAX_VALUE_LENGTH.
        """
        small_bytes = b"hello world"
        self.assert_roundtrips(self.CommandWithBigArgument, big=small_bytes)

    def test_roundtrip_medium(self):
        """
        ``Big`` can serialize and unserialize argmuments which are larger than
        MAX_VALUE_LENGTH.
        """
        medium_bytes = b"x" * (MAX_VALUE_LENGTH + 1)
        self.assert_roundtrips(self.CommandWithBigArgument, big=medium_bytes)

    def test_roundtrip_large(self):
        """
        ``Big`` can serialize and unserialize argmuments which are larger than
        MAX_VALUE_LENGTH.
        """
        big_bytes = u"\n".join(
            u"{value}".format(value=value)
            for value
            in range(MAX_VALUE_LENGTH)
        ).encode("ascii")

        self.assert_roundtrips(self.CommandWithBigArgument, big=big_bytes)

    def test_two_big_arguments(self):
        """
        AMP can serialize and unserialize a ``Command`` with multiple ``Big``
        arguments.
        """
        self.assert_roundtrips(
            self.CommandWithTwoBigArgument,
            big=b"hello world",
            large=b"goodbye world",
        )

    def test_big_and_regular_arguments(self):
        """
        AMP can serialize and unserialize a ``Command`` with a combination of
        ``Big`` and regular arguments.
        """
        self.assert_roundtrips(
            self.CommandWithBigAndRegularArgument,
            big=b"hello world",
            regular=b"goodbye world",
        )


class SerializationTests(TestCase):
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
        argument = SerializableArgument(NodeState, Deployment)
        objects = [TEST_DEPLOYMENT, NODE_STATE]
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

    def test_caches(self):
        """
        Encoding results are cached.
        """
        argument = SerializableArgument(Deployment)
        # This is a fragile assertion since it assumes a particular
        # implementation of strings in Python... Some implementations may
        # choose to reuse string objects separately from our use of a
        # cache. On CPython 2.7 it fails when caching is disabled, at
        # least.
        self.assertIs(argument.toString(TEST_DEPLOYMENT),
                      argument.toString(TEST_DEPLOYMENT))


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
        reactor, FilePath(test.mktemp()))
    persistence_service.startService()
    test.addCleanup(persistence_service.stopService)
    return ControlAMPService(reactor, cluster_state, persistence_service,
                             TCP4ServerEndpoint(MemoryReactor(), 1234),
                             # Easiest TLS context factory to create:
                             ClientContextFactory())


class ControlTestCase(TestCase):
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


class StringTransportWithAbort(StringTransport):
    """
    A ``StringTransport`` that implements ``abortConnection``.
    """
    def __init__(self, *args, **kwargs):
        self.aborted = False
        StringTransport.__init__(self, *args, **kwargs)

    def abortConnection(self):
        self.aborted = True
        self.connected = False


class ControlAMPTests(ControlTestCase):
    """
    Tests for ``ControlAMP`` and ``ControlServiceLocator``.
    """
    def setUp(self):
        super(ControlAMPTests, self).setUp()
        self.reactor = Clock()
        self.control_amp_service = build_control_amp_service(
            self, self.reactor,
        )
        self.protocol = ControlAMP(self.reactor, self.control_amp_service)
        self.client = LoopbackAMPClient(self.protocol.locator)

    def test_connection_stays_open_on_activity(self):
        """
        The AMP connection remains open when communication is received at
        any time up to the timeout limit.
        """
        self.protocol.makeConnection(StringTransportWithAbort())
        initially_aborted = self.protocol.transport.aborted
        advance_some(self.reactor)
        self.client.callRemote(NoOp)
        self.reactor.advance(PING_INTERVAL.seconds * 1.9)
        # This NoOp will reset the timeout.
        self.client.callRemote(NoOp)
        self.reactor.advance(PING_INTERVAL.seconds * 1.9)
        later_aborted = self.protocol.transport.aborted
        self.assertEqual(
            dict(initially=initially_aborted, later=later_aborted),
            dict(initially=False, later=False)
        )

    def test_connection_closed_on_no_activity(self):
        """
        If no communication has been received for long enough that we expire
        cluster state, the silent connection is forcefully closed.
        """
        self.protocol.makeConnection(StringTransportWithAbort())
        advance_some(self.reactor)
        self.client.callRemote(NoOp)
        self.assertFalse(self.protocol.transport.aborted)
        self.reactor.advance(PING_INTERVAL.seconds * 2)
        self.assertEqual(self.protocol.transport.aborted, True)

    def test_connection_made(self):
        """
        When a connection is made the ``ControlAMP`` is added to the services
        set of connections.
        """
        marker = object()
        self.control_amp_service.connections.add(marker)
        current = self.control_amp_service.connections.copy()
        self.protocol.makeConnection(StringTransportWithAbort())
        self.assertEqual((current, self.control_amp_service.connections),
                         ({marker}, {marker, self.protocol}))

    @capture_logging(assertHasAction, AGENT_CONNECTED, succeeded=True)
    def test_connection_made_send_cluster_status(self, logger):
        """
        When a connection is made the cluster status is sent to the new client.
        """
        sent = []
        self.patch_call_remote(sent, self.protocol)
        self.control_amp_service.configuration_service.save(TEST_DEPLOYMENT)
        self.control_amp_service.cluster_state.apply_changes([NODE_STATE])

        self.protocol.makeConnection(StringTransportWithAbort())
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
        self.protocol.makeConnection(StringTransportWithAbort())
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
        self.protocol.makeConnection(StringTransportWithAbort())
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

        agents = [FakeAgent(), FakeAgent()]
        clients = list(AgentAMP(Clock(), agent) for agent in agents)
        servers = list(LoopbackAMPClient(client.locator) for client in clients)

        for server in servers:
            delayed = DelayedAMPClient(server)
            self.control_amp_service.connected(delayed)
            delayed.respond()

        self.successResultOf(
            self.client.callRemote(NodeStateCommand,
                                   state_changes=(NODE_STATE,),
                                   eliot_context=TEST_ACTION))

        cluster_state = self.control_amp_service.cluster_state.as_deployment()
        expected = dict(configuration=TEST_DEPLOYMENT, state=cluster_state)
        self.assertEqual(
            [expected] * len(agents),
            list(
                dict(configuration=agent.desired, state=agent.actual)
                for agent in agents
            ),
        )

    def test_too_long_node_state(self):
        """
        AMP protocol can transmit node states with 800 applications.
        """
        node_prototype = NodeState(
            hostname=u"192.0.3.13", uuid=uuid4(), applications=[],
        )
        node = huge_node(node_prototype)
        d = self.client.callRemote(
            NodeStateCommand,
            state_changes=(node,),
            eliot_context=TEST_ACTION,
        )
        self.successResultOf(d)
        self.assertEqual(
            DeploymentState(nodes=[node]),
            self.control_amp_service.cluster_state.as_deployment(),
        )

    def test_set_node_era(self):
        """
        A ``SetNodeEraCommand`` results in the node's era being
        updated.
        """
        node_uuid = uuid4()
        era = uuid4()
        d = self.client.callRemote(SetNodeEraCommand,
                                   node_uuid=unicode(node_uuid),
                                   era=unicode(era))
        self.successResultOf(d)
        self.assertEqual(
            DeploymentState(node_uuid_to_era={node_uuid: era}),
            self.control_amp_service.cluster_state.as_deployment(),
        )


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
            c.makeConnection(StringTransportWithAbort())
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
        agent = FakeAgent()
        client = AgentAMP(Clock(), agent)
        service = build_control_amp_service(self)
        service.startService()
        server = LoopbackAMPClient(client.locator)
        service.connected(server)

        service.configuration_service.save(TEST_DEPLOYMENT)

        self.assertEqual(
            dict(configuration=TEST_DEPLOYMENT, state=DeploymentState()),
            dict(configuration=agent.desired, state=agent.actual),
        )

    def test_second_configuration_change_waits_for_first_acknowledgement(self):
        """
        A second configuration change is only transmitted after acknowledgement
        of the first configuration change is received.
        """
        agent = FakeAgent()
        client = AgentAMP(Clock(), agent)
        service = build_control_amp_service(self)
        service.startService()

        # Add a second agent, to ensure that the delayed logic interacts with
        # the correct connection.
        confounding_agent = FakeAgent()
        confounding_client = AgentAMP(Clock(), confounding_agent)
        confounding_server = LoopbackAMPClient(confounding_client.locator)
        service.connected(confounding_server)

        configuration = service.configuration_service.get()
        modified_configuration = arbitrary_transformation(configuration)

        server = LoopbackAMPClient(client.locator)
        delayed_server = DelayedAMPClient(server)
        # Send first update
        service.connected(delayed_server)
        first_agent_desired = agent.desired

        # Send second update
        service.configuration_service.save(modified_configuration)
        second_agent_desired = agent.desired

        delayed_server.respond()
        third_agent_desired = agent.desired

        self.assertEqual(
            dict(
                first=configuration,
                second=configuration,
                third=modified_configuration,
            ),
            dict(
                first=first_agent_desired,
                second=second_agent_desired,
                third=third_agent_desired,
            ),
        )

    def test_second_configuration_change_suceeds_when_first_fails(self):
        """
        If the first update fails, we want to ensure that following updates
        won't get stuck waiting, and will get updated.
        """
        agent = FakeAgent()
        client = AgentAMP(Clock(), agent)
        service = build_control_amp_service(self)
        service.startService()

        # Add a second agent, to ensure that the delayed logic interacts with
        # the correct connection.
        confounding_agent = FakeAgent()
        confounding_client = AgentAMP(Clock(), confounding_agent)

        # Setup of the the server that will fail to update
        failing_server = LoopbackAMPClient(confounding_client.locator)

        def raise_unexpected_exception(self,
                                       commandType=None,
                                       *a, **kw):
            raise Exception("I'm an unexpected exception")

        # We want the update to fail in one of the connections
        self.patch(failing_server,
                   "callRemote",
                   raise_unexpected_exception
                   )
        # The connection will fail, but it shouldn't prevent following
        # commnads (from ``delayed_server``) to be properly executed
        service.connected(failing_server)

        configuration = service.configuration_service.get()
        modified_configuration = arbitrary_transformation(configuration)

        server = LoopbackAMPClient(client.locator)
        delayed_server = DelayedAMPClient(server)
        # Send first update
        service.connected(delayed_server)

        # Send second update
        service.configuration_service.save(modified_configuration)
        second_agent_desired = agent.desired

        delayed_server.respond()
        third_agent_desired = agent.desired

        # Now we verify that the updates following the failure
        # actually worked as we expect
        self.assertEqual(
            dict(
                first=configuration,
                second=modified_configuration,
            ),
            dict(
                # The update will fail, so we don't expect the config to change
                first=second_agent_desired,
                second=third_agent_desired,
            ),
        )

    def test_third_configuration_change_supercedes_second(self):
        """
        A third configuration change completely replaces a second configuration
        change if the first configuration change has not yet been acknowledged.
        """
        agent = FakeAgent()
        client = AgentAMP(Clock(), agent)
        service = build_control_amp_service(self)
        service.startService()

        # Add a second agent, to ensure that the delayed logic interacts with
        # the correct connection.
        confounding_agent = FakeAgent()
        confounding_client = AgentAMP(Clock(), confounding_agent)
        confounding_server = LoopbackAMPClient(confounding_client.locator)
        service.connected(confounding_server)

        configuration = service.configuration_service.get()
        modified_configuration = arbitrary_transformation(configuration)
        more_modified_configuration = arbitrary_transformation(
            modified_configuration
        )

        server = LoopbackAMPClient(client.locator)
        delayed_server = DelayedAMPClient(server)
        # Send first update
        service.connected(delayed_server)
        # Send second update
        service.configuration_service.save(modified_configuration)
        # Send third update
        service.configuration_service.save(more_modified_configuration)

        first_agent_desired = agent.desired
        delayed_server.respond()
        second_agent_desired = agent.desired
        delayed_server.respond()
        third_agent_desired = agent.desired

        # Only two calls should be required because only two states should be
        # sent.  The intermediate state should never get sent.
        self.assertRaises(IndexError, delayed_server.respond)

        self.assertEqual(
            [configuration,
             more_modified_configuration,
             more_modified_configuration],
            [first_agent_desired,
             second_agent_desired,
             third_agent_desired],
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


class AgentClientTests(TestCase):
    """
    Tests for ``AgentAMP``.
    """
    def setUp(self):
        super(AgentClientTests, self).setUp()
        self.agent = FakeAgent()
        self.reactor = Clock()
        self.client = AgentAMP(self.reactor, self.agent)
        self.client.makeConnection(StringTransportWithAbort())
        # The server needs to send commands to the client, so it acts as
        # an AMP client in that regard. Due to https://tm.tl/7761 we need
        # to access the passed in locator directly.
        self.server = LoopbackAMPClient(self.client.locator)

    def test_connection_stays_open_on_activity(self):
        """
        The AMP connection remains open when communication is received at
        any time up to the timeout limit.
        """
        advance_some(self.reactor)
        self.server.callRemote(NoOp)
        self.reactor.advance(PING_INTERVAL.seconds * 1.9)
        # This NoOp will reset the timeout.
        self.server.callRemote(NoOp)
        self.reactor.advance(PING_INTERVAL.seconds * 1.9)
        self.assertEqual(self.client.transport.aborted, False)

    def test_connection_closed_on_no_activity(self):
        """
        If no communication has been received for long enough that we expire
        cluster state, the silent connection is forcefully closed.
        """
        advance_some(self.reactor)
        self.server.callRemote(NoOp)
        self.reactor.advance(PING_INTERVAL.seconds * 2)
        self.assertEqual(self.client.transport.aborted, True)

    def test_initially_not_connected(self):
        """
        The agent does not get told a connection was made or lost before it's
        actually happened.
        """
        self.agent = FakeAgent()
        self.reactor = Clock()
        self.client = AgentAMP(self.reactor, self.agent)
        self.assertEqual(self.agent, FakeAgent(is_connected=False,
                                               is_disconnected=False))

    def test_connection_made(self):
        """
        Connection made events are passed on to the agent.
        """
        self.assertEqual(self.agent, FakeAgent(is_connected=True,
                                               client=self.client))

    def test_connection_lost(self):
        """
        Connection lost events are passed on to the agent.
        """
        self.client.connectionLost(Failure(ConnectionLost()))
        self.assertEqual(self.agent, FakeAgent(is_connected=True,
                                               is_disconnected=True))

    def test_too_long_configuration(self):
        """
        AMP protocol can transmit configurations with 800 applications.
        """
        actual = DeploymentState(nodes=[])
        configuration = huge_deployment()
        d = self.server.callRemote(
            ClusterStatusCommand,
            configuration=configuration,
            state=actual,
            eliot_context=TEST_ACTION
        )

        self.successResultOf(d)
        self.assertEqual(configuration, self.agent.desired)

    def test_too_long_state(self):
        """
        AMP protocol can transmit states with 800 applications.
        """
        state = huge_state()
        d = self.server.callRemote(
            ClusterStatusCommand,
            configuration=Deployment(),
            state=state,
            eliot_context=TEST_ACTION,
        )
        self.successResultOf(d)
        self.assertEqual(state, self.agent.actual)

    def test_cluster_updated(self):
        """
        ``ClusterStatusCommand`` sent to the ``AgentClient`` result in agent
        having cluster state updated.
        """
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
    class IConvergenceAgentTests(TestCase):
        """
        Tests for ``IConvergenceAgent``.
        """
        def test_connected(self):
            """
            ``IConvergenceAgent.connected()`` takes an AMP instance.
            """
            agent = fixture(self)
            agent.connected(connected_amp_protocol())

        def test_disconnected(self):
            """
            ``IConvergenceAgent.disconnected()`` can be called after
            ``IConvergenceAgent.connected()``.
            """
            agent = fixture(self)
            agent.connected(connected_amp_protocol())
            agent.disconnected()

        def test_reconnected(self):
            """
            ``IConvergenceAgent.connected()`` can be called after
            ``IConvergenceAgent.disconnected()``.
            """
            agent = fixture(self)
            agent.connected(connected_amp_protocol())
            agent.disconnected()
            agent.connected(connected_amp_protocol())

        def test_cluster_updated(self):
            """
            ``IConvergenceAgent.cluster_updated()`` takes two ``Deployment``
            instances.
            """
            agent = fixture(self)
            agent.connected(connected_amp_protocol())
            agent.cluster_updated(
                Deployment(nodes=frozenset()), DeploymentState(nodes=[]))

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


class ClusterStatusCommandTests(TestCase):
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


class AgentLocatorTests(TestCase):
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
        reactor = Clock()
        protocol = AgentAMP(reactor, fake_agent)
        locator = _AgentLocator(
            agent=fake_agent, timeout=timeout_for_protocol(reactor, protocol))
        self.assertIs(logger, locator.logger)


class ControlServiceLocatorTests(TestCase):
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
        reactor = Clock()
        protocol = ControlAMP(reactor, fake_control_amp_service)
        locator = ControlServiceLocator(
            reactor=reactor,
            control_amp_service=fake_control_amp_service,
            timeout=timeout_for_protocol(reactor, protocol)
        )
        self.assertIs(logger, locator.logger)


class SendStateToConnectionsTests(TestCase):
    """
    Tests for ``ControlAMPService._send_state_to_connections``.
    """
    @capture_logging(None)
    def test_logging(self, logger):
        """
        ``_send_state_to_connections`` logs a single LOG_SEND_CLUSTER_STATE
        action and a LOG_SEND_TO_AGENT action for the remote calls to each of
        its connections.
        """
        control_amp_service = build_control_amp_service(self)

        agent = FakeAgent()
        client = AgentAMP(Clock(), agent)
        server = LoopbackAMPClient(client.locator)

        control_amp_service.connected(server)
        control_amp_service._send_state_to_connections(connections=[server])

        assertHasAction(
            self,
            logger,
            LOG_SEND_CLUSTER_STATE,
            succeeded=True,
            endFields={
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
            startFields={"agent": server},
        )


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
            peer.callRemote(NoOp)  # Keep the other side alive past its timeout
            pump.flush()
        self.assertEqual(locator.noops, expected_pings)

    def test_stop_pinging_on_connection_lost(self):
        """
        When the protocol loses its connection, it stops trying to send
        ``NoOp`` commands.
        """
        reactor = Clock()
        protocol = self.build_protocol(reactor)
        transport = StringTransportWithAbort()
        protocol.makeConnection(transport)
        transport.clear()
        protocol.connectionLost(Failure(ConnectionDone("test, simulated")))
        reactor.advance(PING_INTERVAL.total_seconds())
        self.assertEqual(b"", transport.value())


class ControlAMPPingTests(TestCase, PingTestsMixin):
    """
    Tests for pinging done by ``ControlAMP``.
    """
    def build_protocol(self, reactor):
        control_amp_service = build_control_amp_service(
            self, reactor,
        )
        return ControlAMP(reactor, control_amp_service)


class AgentAMPPingTests(TestCase, PingTestsMixin):
    """
    Tests for pinging done by ``AgentAMP``.
    """
    def build_protocol(self, reactor):
        return AgentAMP(reactor, FakeAgent())


class CachingWireEncodeTests(TestCase):
    """
    Tests for ``caching_wire_encode``.
    """
    def test_encodes(self):
        """
        ``CachingEncoder.encode`` returns result of ``wire_encode`` for given
        object.
        """
        self.assertEqual(
            [loads(caching_wire_encode(TEST_DEPLOYMENT)),
             loads(caching_wire_encode(NODE_STATE))],
            [loads(wire_encode(TEST_DEPLOYMENT)),
             loads(wire_encode(NODE_STATE))])

    def test_caches(self):
        """
        ``CachingEncoder.encode`` caches the result of ``wire_encode`` for a
        particular object if used in context of ``cache()``.
        """
        # Warm up cache:
        result1 = caching_wire_encode(TEST_DEPLOYMENT)
        result2 = caching_wire_encode(NODE_STATE)

        self.assertEqual(
            [loads(result1) == loads(wire_encode(TEST_DEPLOYMENT)),
             loads(result2) == loads(wire_encode(NODE_STATE)),
             caching_wire_encode(TEST_DEPLOYMENT) is result1,
             caching_wire_encode(NODE_STATE) is result2],
            [True, True, True, True])
