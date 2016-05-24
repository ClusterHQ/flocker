# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for ``flocker.node._container``.
"""

from uuid import UUID, uuid4

from ipaddr import IPAddress

from pyrsistent import pset, pvector

from bitmath import GiB

from eliot.testing import capture_logging

from twisted.internet.defer import FirstError
from twisted.python.filepath import FilePath

from .. import (
    ApplicationNodeDeployer, NoOp, NOOP_SLEEP_TIME
)
from ..testtools import (
    EMPTY,
    EMPTY_STATE, empty_node_local_state,
    assert_calculated_changes_for_deployer, to_node,
)
from ...testtools import TestCase
from ...control import (
    Application, DockerImage, Deployment, Node, Port, Link,
    NodeState, DeploymentState, RestartNever, RestartAlways, RestartOnFailure
)

from .. import sequentially, in_parallel

from .._deploy import (
    NodeLocalState,
)
from .._container import (
    StartApplication, StopApplication, SetProxies, _link_environment, OpenPorts
)
from ...control.testtools import InMemoryStatePersister
from ...control._model import (
    AttachedVolume, Dataset, Manifestation, PersistentState,
)
from .._docker import (
    FakeDockerClient, AlreadyExists, Unit, PortMap, Environment,
    DockerClient, Volume as DockerVolume)
from ...route import Proxy, OpenPort, make_memory_network
from ...route._iptables import HostNetwork

from .istatechange import make_istatechange_tests


# This models an application without a volume.
APPLICATION_WITHOUT_VOLUME = Application(
    name=u"stateless",
    image=DockerImage.from_string(u"clusterhq/testing-stateless"),
    volume=None,
)

# This models an application that has a volume.
APPLICATION_WITH_VOLUME_NAME = u"psql-clusterhq"
DATASET_ID = unicode(uuid4())
DATASET = Dataset(dataset_id=DATASET_ID)
APPLICATION_WITH_VOLUME_MOUNTPOINT = FilePath(b"/var/lib/postgresql")
APPLICATION_WITH_VOLUME_IMAGE = u"clusterhq/postgresql:9.1"
APPLICATION_WITH_VOLUME = Application(
    name=APPLICATION_WITH_VOLUME_NAME,
    image=DockerImage.from_string(APPLICATION_WITH_VOLUME_IMAGE),
    volume=AttachedVolume(
        manifestation=Manifestation(dataset=DATASET, primary=True),
        mountpoint=APPLICATION_WITH_VOLUME_MOUNTPOINT,
    ),
    links=frozenset(),
)
MANIFESTATION = APPLICATION_WITH_VOLUME.volume.manifestation

DATASET_WITH_SIZE = Dataset(dataset_id=DATASET_ID,
                            metadata=DATASET.metadata,
                            maximum_size=1024 * 1024 * 100)

APPLICATION_WITH_VOLUME_SIZE = Application(
    name=APPLICATION_WITH_VOLUME_NAME,
    image=DockerImage.from_string(APPLICATION_WITH_VOLUME_IMAGE),
    volume=AttachedVolume(
        manifestation=Manifestation(dataset=DATASET_WITH_SIZE,
                                    primary=True),
        mountpoint=APPLICATION_WITH_VOLUME_MOUNTPOINT,
    ),
    links=frozenset(),
)


def assert_application_calculated_changes(
    case, node_state, node_config, nonmanifest_datasets, expected_changes,
    additional_node_states=frozenset(), additional_node_config=frozenset(),
):
    """
    Assert that ``ApplicationNodeDeployer`` calculates certain changes in a
    certain circumstance.

    :see: ``assert_calculated_changes_for_deployer``.
    """
    deployer = ApplicationNodeDeployer(
        hostname=node_state.hostname,
        node_uuid=node_state.uuid,
        docker_client=FakeDockerClient(),
        network=make_memory_network(),
    )
    return assert_calculated_changes_for_deployer(
        case, deployer, node_state, node_config, nonmanifest_datasets,
        additional_node_states, additional_node_config, expected_changes,
        NodeLocalState(node_state=node_state)
    )


class ApplicationNodeDeployerAttributesTests(TestCase):
    """
    Tests for attributes and initialiser arguments of
    `ApplicationNodeDeployer`.
    """
    def test_docker_client_default(self):
        """
        ``ApplicationNodeDeployer.docker_client`` is a ``DockerClient`` by
        default.
        """
        self.assertIsInstance(
            ApplicationNodeDeployer(u"example.com", None).docker_client,
            DockerClient
        )

    def test_docker_override(self):
        """
        ``ApplicationNodeDeployer.docker_client`` can be overridden in the
        constructor.
        """
        dummy_docker_client = object()
        self.assertIs(
            dummy_docker_client,
            ApplicationNodeDeployer(
                u'example.com',
                docker_client=dummy_docker_client).docker_client
        )

    def test_network_default(self):
        """
        ``ApplicationNodeDeployer._network`` is a ``HostNetwork`` by default.
        """
        self.assertIsInstance(
            ApplicationNodeDeployer(u'example.com', None).network,
            HostNetwork)

    def test_network_override(self):
        """
        ``ApplicationNodeDeployer._network`` can be overridden in the
        constructor.
        """
        dummy_network = object()
        self.assertIs(
            dummy_network,
            ApplicationNodeDeployer(u'example.com',
                                    network=dummy_network).network
        )


StartApplicationIStateChangeTests = make_istatechange_tests(
    StartApplication,
    dict(
        application=APPLICATION_WITH_VOLUME,
        node_state=NodeState(hostname="node1.example.com")
    ),
    dict(
        application=APPLICATION_WITH_VOLUME.set(name=u"throwaway-app"),
        node_state=NodeState(hostname="node2.example.com")
    )
)
StopApplicationIStageChangeTests = make_istatechange_tests(
    StopApplication,
    dict(application=APPLICATION_WITH_VOLUME),
    dict(application=APPLICATION_WITH_VOLUME.set(name=u"throwaway-app")),
)
SetProxiesIStateChangeTests = make_istatechange_tests(
    SetProxies,
    dict(ports=[Proxy(ip=IPAddress("10.0.0.1"), port=1000)]),
    dict(ports=[Proxy(ip=IPAddress("10.0.0.2"), port=2000)]),
)


class StartApplicationTests(TestCase):
    """
    Tests for ``StartApplication``.
    """
    def test_start(self):
        """
        ``StartApplication`` accepts an application object and when ``run()``
        is called returns a ``Deferred`` which fires when the docker container
        has been added and started.
        """
        fake_docker = FakeDockerClient()
        api = ApplicationNodeDeployer(u'example.com',
                                      docker_client=fake_docker)
        docker_image = DockerImage(repository=u'clusterhq/flocker',
                                   tag=u'release-14.0')
        ports = frozenset([Port(internal_port=80, external_port=8080)])
        application = Application(
            name=u'site-example.com',
            image=docker_image,
            ports=ports,
            links=frozenset(),
        )
        start_result = StartApplication(
            application=application,
            node_state=EMPTY_NODESTATE
        ).run(api, state_persister=InMemoryStatePersister())
        exists_result = fake_docker.exists(unit_name=application.name)

        port_maps = pset(
            [PortMap(internal_port=80, external_port=8080)]
        )
        self.assertEqual(
            (None, True, docker_image.full_name, port_maps),
            (self.successResultOf(start_result),
             self.successResultOf(exists_result),
             fake_docker._units[application.name].container_image,
             fake_docker._units[application.name].ports)
        )

    def test_already_exists(self):
        """
        ``StartApplication.run`` returns a `Deferred` which errbacks with
        an ``AlreadyExists`` error if there is already a unit with the supplied
        application name.
        """
        api = ApplicationNodeDeployer(u'example.com',
                                      docker_client=FakeDockerClient())
        application = Application(
            name=u'site-example.com',
            image=DockerImage(repository=u'clusterhq/flocker',
                              tag=u'release-14.0'),
            links=frozenset(),
        )

        result1 = StartApplication(
            application=application,
            node_state=EMPTY_NODESTATE
        ).run(api, state_persister=InMemoryStatePersister())
        self.successResultOf(result1)

        result2 = StartApplication(
            application=application,
            node_state=EMPTY_NODESTATE
        ).run(api, state_persister=InMemoryStatePersister())
        self.failureResultOf(result2, AlreadyExists)

    def test_environment_supplied_to_docker(self):
        """
        ``StartApplication.run()`` passes the environment dictionary of the
        application to ``DockerClient.add`` as an ``Environment`` instance.
        """
        fake_docker = FakeDockerClient()
        deployer = ApplicationNodeDeployer(u'example.com', fake_docker)

        application_name = u'site-example.com'
        variables = frozenset({u'foo': u"bar", u"baz": u"qux"}.iteritems())
        application = Application(
            name=application_name,
            image=DockerImage(repository=u'clusterhq/postgresql',
                              tag=u'9.3.5'),
            environment=variables.copy(),
            links=frozenset(),
            ports=(),
        )

        StartApplication(
            application=application,
            node_state=EMPTY_NODESTATE,
        ).run(deployer, state_persister=InMemoryStatePersister())

        expected_environment = Environment(variables=variables.copy())

        self.assertEqual(
            expected_environment,
            fake_docker._units[application_name].environment
        )

    def test_environment_not_supplied(self):
        """
        ``StartApplication.run()`` only passes an ``Environment`` instance
        if the application defines an environment.
        """
        fake_docker = FakeDockerClient()
        deployer = ApplicationNodeDeployer(u'example.com', fake_docker)

        application_name = u'site-example.com'
        application = Application(
            name=application_name,
            image=DockerImage(repository=u'clusterhq/postgresql',
                              tag=u'9.3.5'),
            environment=None,
            links=frozenset(),
        )

        StartApplication(
            application=application,
            node_state=EMPTY_NODESTATE,
        ).run(deployer, state_persister=InMemoryStatePersister())

        self.assertEqual(
            None,
            fake_docker._units[application_name].environment
        )

    def test_links(self):
        """
        ``StartApplication.run()`` passes environment variables to connect to
        the remote application to ``DockerClient.add``.
        """
        fake_docker = FakeDockerClient()
        deployer = ApplicationNodeDeployer(u'example.com', fake_docker)

        application_name = u'site-example.com'
        application = Application(
            name=application_name,
            image=DockerImage(repository=u'clusterhq/postgresql',
                              tag=u'9.3.5'),
            links=frozenset([Link(alias="alias", local_port=80,
                                  remote_port=8080)]))

        StartApplication(
            application=application,
            node_state=EMPTY_NODESTATE,
        ).run(deployer, state_persister=InMemoryStatePersister())

        variables = frozenset({
            'ALIAS_PORT_80_TCP': 'tcp://example.com:8080',
            'ALIAS_PORT_80_TCP_ADDR': 'example.com',
            'ALIAS_PORT_80_TCP_PORT': '8080',
            'ALIAS_PORT_80_TCP_PROTO': 'tcp',
        }.iteritems())
        expected_environment = Environment(variables=variables.copy())

        self.assertEqual(
            expected_environment,
            fake_docker._units[application_name].environment
        )

    def test_volumes(self):
        """
        ``StartApplication.run()`` passes the appropriate volume arguments to
        ``DockerClient.add`` based on the application's volume.
        """
        DATASET_ID = unicode(uuid4())
        fake_docker = FakeDockerClient()
        deployer = ApplicationNodeDeployer(u'example.com', fake_docker)
        node_path = FilePath(b"/flocker/" + DATASET_ID.encode("ascii"))

        mountpoint = FilePath(b"/mymount")
        application_name = u'site-example.com'
        application = Application(
            name=application_name,
            image=DockerImage(repository=u'clusterhq/postgresql',
                              tag=u'9.3.5'),
            links=frozenset(),
            volume=AttachedVolume(
                manifestation=Manifestation(
                    dataset=Dataset(dataset_id=DATASET_ID),
                    primary=True),
                mountpoint=mountpoint))

        StartApplication(
            application=application,
            node_state=EMPTY_NODESTATE.set(
                "paths", {DATASET_ID: node_path}),
        ).run(deployer, state_persister=InMemoryStatePersister())

        self.assertEqual(
            pset([DockerVolume(node_path=node_path,
                               container_path=mountpoint)]),
            fake_docker._units[application_name].volumes
        )

    def test_memory_limit(self):
        """
        ``StartApplication.run()`` passes an ``Application``'s mem_limit to
        ``DockerClient.add`` which is used when creating a Unit.
        """
        EXPECTED_MEMORY_LIMIT = 100000000
        fake_docker = FakeDockerClient()
        deployer = ApplicationNodeDeployer(u'example.com', fake_docker)

        application_name = u'site-example.com'
        application = Application(
            name=application_name,
            image=DockerImage(repository=u'clusterhq/postgresql',
                              tag=u'9.3.5'),
            environment=None,
            links=frozenset(),
            memory_limit=EXPECTED_MEMORY_LIMIT
        )

        StartApplication(
            application=application,
            node_state=EMPTY_NODESTATE,
        ).run(deployer, state_persister=InMemoryStatePersister())

        self.assertEqual(
            EXPECTED_MEMORY_LIMIT,
            fake_docker._units[application_name].mem_limit
        )

    def test_cpu_shares(self):
        """
        ``StartApplication.run()`` passes an ``Application``'s cpu_shares to
        ``DockerClient.add`` which is used when creating a Unit.
        """
        EXPECTED_CPU_SHARES = 512
        fake_docker = FakeDockerClient()
        deployer = ApplicationNodeDeployer(u'example.com', fake_docker)

        application_name = u'site-example.com'
        application = Application(
            name=application_name,
            image=DockerImage(repository=u'clusterhq/postgresql',
                              tag=u'9.3.5'),
            environment=None,
            links=frozenset(),
            cpu_shares=EXPECTED_CPU_SHARES
        )

        StartApplication(
            application=application,
            node_state=EMPTY_NODESTATE,
        ).run(deployer, state_persister=InMemoryStatePersister())

        self.assertEqual(
            EXPECTED_CPU_SHARES,
            fake_docker._units[application_name].cpu_shares
        )

    def test_restart_policy(self):
        """
        ``StartApplication.run()`` passes ``RestartNever`` to
        ``DockerClient.add`` which is used when creating a Unit.

        It doesn't pass the ``Application``\ 's ``restart_policy`` because
        ``RestartNever`` is the only implemented policy.  See FLOC-2449.
        """
        policy = RestartAlways()
        fake_docker = FakeDockerClient()
        deployer = ApplicationNodeDeployer(u'example.com', fake_docker)

        application_name = u'site-example.com'
        application = Application(
            name=application_name,
            image=DockerImage(repository=u'clusterhq/postgresql',
                              tag=u'9.3.5'),
            restart_policy=policy,
        )

        StartApplication(
            application=application,
            node_state=EMPTY_NODESTATE,
        ).run(deployer, state_persister=InMemoryStatePersister())

        [unit] = self.successResultOf(fake_docker.list())
        self.assertEqual(
            unit.restart_policy,
            RestartNever())

    def test_command_line(self):
        """
        ``StartApplication.run()`` passes an ``Application``'s
        ``command_line`` to ``DockerClient.add``.
        """
        command_line = [u"hello", u"there"]
        fake_docker = FakeDockerClient()
        deployer = ApplicationNodeDeployer(u'example.com', fake_docker)

        application_name = u'site-example.com'
        application = Application(
            name=application_name,
            image=DockerImage.from_string(u"postgresql"),
            command_line=command_line)

        StartApplication(
            application=application,
            node_state=EMPTY_NODESTATE,
        ).run(deployer, state_persister=InMemoryStatePersister())

        self.assertEqual(
            fake_docker._units[application_name].command_line,
            pvector(command_line),
        )


class LinkEnviromentTests(TestCase):
    """
    Tests for ``_link_environment``.
    """

    def test_link_environment(self):
        """
        ``_link_environment(link)`` returns a dictonary
        with keys used by docker to represent links. Specifically
        ``<alias>_PORT_<local_port>_<protocol>`` and the broken out variants
        ``_ADDR``, ``_PORT`` and ``_PROTO``.
        """
        environment = _link_environment(
            protocol="tcp",
            alias="somealias",
            local_port=80,
            hostname=u"the-host",
            remote_port=8080)
        self.assertEqual(
            environment,
            {
                u'SOMEALIAS_PORT_80_TCP': u'tcp://the-host:8080',
                u'SOMEALIAS_PORT_80_TCP_PROTO': u'tcp',
                u'SOMEALIAS_PORT_80_TCP_ADDR': u'the-host',
                u'SOMEALIAS_PORT_80_TCP_PORT': u'8080',
            })


class StopApplicationTests(TestCase):
    """
    Tests for ``StopApplication``.
    """
    def test_stop(self):
        """
        ``StopApplication`` accepts an application object and when ``run()``
        is called returns a ``Deferred`` which fires when the container
        has been removed.
        """
        fake_docker = FakeDockerClient()
        api = ApplicationNodeDeployer(u'example.com',
                                      docker_client=fake_docker)
        application = Application(
            name=u'site-example.com',
            image=DockerImage(repository=u'clusterhq/flocker',
                              tag=u'release-14.0'),
            links=frozenset(),
        )

        StartApplication(
            application=application,
            node_state=EMPTY_NODESTATE
        ).run(api, state_persister=InMemoryStatePersister())
        existed = fake_docker.exists(application.name)
        stop_result = StopApplication(
            application=application,
        ).run(api, state_persister=InMemoryStatePersister())
        exists_result = fake_docker.exists(unit_name=application.name)

        self.assertEqual(
            (None, True, False),
            (self.successResultOf(stop_result),
             self.successResultOf(existed),
             self.successResultOf(exists_result))
        )

    def test_does_not_exist(self):
        """
        ``StopApplication.run()`` does not errback if the application does
        not exist.
        """
        api = ApplicationNodeDeployer(u'example.com',
                                      docker_client=FakeDockerClient())
        application = Application(
            name=u'site-example.com',
            image=DockerImage(repository=u'clusterhq/flocker',
                              tag=u'release-14.0'),
            links=frozenset(),
        )
        result = StopApplication(
            application=application,
        ).run(api, state_persister=InMemoryStatePersister())
        result = self.successResultOf(result)

        self.assertIs(None, result)
APP_NAME = u"site-example.com"
UNIT_FOR_APP = Unit(name=APP_NAME,
                    container_name=APP_NAME,
                    container_image=u"flocker/wordpress:latest",
                    activation_state=u'active')
APP = Application(
    name=APP_NAME,
    image=DockerImage.from_string(UNIT_FOR_APP.container_image)
)
APP_NAME2 = u"site-example.net"
UNIT_FOR_APP2 = Unit(name=APP_NAME2,
                     container_name=APP_NAME2,
                     container_image=u"flocker/wordpress:latest",
                     activation_state=u'active')
APP2 = Application(
    name=APP_NAME2,
    image=DockerImage.from_string(UNIT_FOR_APP2.container_image)
)
# https://clusterhq.atlassian.net/browse/FLOC-1926
EMPTY_NODESTATE = NodeState(hostname=u"example.com", uuid=uuid4(),
                            manifestations={}, devices={}, paths={},
                            applications=[])


class ApplicationNodeDeployerDiscoverNodeConfigurationTests(
        TestCase):
    """
    Tests for ``ApplicationNodeDeployer.discover_local_state``.
    """
    def setUp(self):
        super(
            ApplicationNodeDeployerDiscoverNodeConfigurationTests, self
        ).setUp()
        self.hostname = u"example.com"
        self.network = make_memory_network()
        self.node_uuid = uuid4()
        # https://clusterhq.atlassian.net/browse/FLOC-1926
        self.EMPTY_NODESTATE = NodeState(
            hostname=self.hostname,
            uuid=self.node_uuid,
            manifestations={}, devices={}, paths={},
            applications=[])

    def _verify_discover_state_applications(
            self, units, expected_applications,
            current_state=None, start_applications=False):
        """
        Given Docker units, verifies that the correct applications are
        discovered on the node by ``discover_state``.

        :param units: ``units`` to pass into the constructor of the
            ``FakeDockerClient``.

        :param expected_applications: A ``PSet`` of ``Application`` instances
            expected to be in the ``NodeState`` returned by ``discover_state``
            given the ``units`` in the ``FakeDockerClient``.

        :param NodeState current_state: The local_state to pass into the call
            of ``discover_state``.

        :param bool start_applications: Whether to run ``StartApplication`` on
            each of the applications before running ``discover_state``.
        """
        if current_state is None:
            current_state = self.EMPTY_NODESTATE
        fake_docker = FakeDockerClient(units=units)
        api = ApplicationNodeDeployer(
            self.hostname,
            node_uuid=self.node_uuid,
            docker_client=fake_docker,
            network=self.network
        )
        if start_applications:
            for app in expected_applications:
                StartApplication(
                    node_state=NodeState(uuid=api.node_uuid,
                                         hostname=api.hostname),
                    application=app
                ).run(api, state_persister=InMemoryStatePersister())
        cluster_state = DeploymentState(nodes={current_state})
        d = api.discover_state(cluster_state,
                               persistent_state=PersistentState())

        self.assertEqual(NodeState(uuid=api.node_uuid, hostname=api.hostname,
                                   applications=expected_applications),
                         self.successResultOf(d).node_state)

    def test_discover_none(self):
        """
        ``ApplicationNodeDeployer.discover_state`` returns an empty
        ``NodeState`` if there are no Docker containers on the host.
        """
        self._verify_discover_state_applications({}, [])

    def test_discover_one(self):
        """
        ``ApplicationNodeDeployer.discover_state`` returns ``NodeState``
        with a a list of running ``Application``\ s; one for each active
        container.
        """
        self._verify_discover_state_applications({APP_NAME: UNIT_FOR_APP},
                                                 [APP])

    def test_discover_multiple(self):
        """
        ``ApplicationNodeDeployer.discover_state`` returns a
        ``NodeState`` with a running ``Application`` for every active
        container on the host.
        """
        units = {APP_NAME: UNIT_FOR_APP, APP_NAME2: UNIT_FOR_APP2}
        applications = [APP, APP2]
        self._verify_discover_state_applications(units, applications)

    def test_discover_application_with_cpushares(self):
        """
        An ``Application`` with a cpu_shares value is discovered from a
        ``Unit`` with a cpu_shares value.
        """
        unit1 = UNIT_FOR_APP.set("cpu_shares", 512)
        units = {unit1.name: unit1}
        applications = [APP.set("cpu_shares", 512)]
        self._verify_discover_state_applications(units, applications)

    def test_discover_application_with_memory_limit(self):
        """
        An ``Application`` with a memory_limit value is discovered from a
        ``Unit`` with a mem_limit value.
        """
        memory_limit = 104857600
        unit1 = UNIT_FOR_APP.set("mem_limit", memory_limit)
        units = {unit1.name: unit1}
        applications = [APP.set("memory_limit", memory_limit)]
        self._verify_discover_state_applications(units, applications)

    def test_discover_application_with_environment(self):
        """
        An ``Application`` with ``Environment`` objects is discovered from a
        ``Unit`` with ``Environment`` objects.
        """
        environment_variables = (
            (b'CUSTOM_ENV_A', b'a value'),
            (b'CUSTOM_ENV_B', b'something else'),
        )
        environment = Environment(variables=environment_variables)
        unit1 = UNIT_FOR_APP.set("environment", environment)
        units = {unit1.name: unit1}
        applications = [APP.set("environment", dict(environment_variables))]
        self._verify_discover_state_applications(units, applications)

    def test_discover_application_with_environment_and_links(self):
        """
        An ``Application`` with ``Environment`` and ``Link`` objects is
        discovered from a ``Unit`` with both custom environment variables and
        environment variables representing container links. The environment
        variables taking the format <ALIAS>_PORT_<PORT>_TCP are separated in
        to ``Link`` representations in the ``Application``.
        """
        environment_variables = (
            (b'CUSTOM_ENV_A', b'a value'),
            (b'CUSTOM_ENV_B', b'something else'),
        )
        link_environment_variables = (
            (b'APACHE_PORT_80_TCP', b'tcp://example.com:8080'),
            (b'APACHE_PORT_80_TCP_PROTO', b'tcp'),
            (b'APACHE_PORT_80_TCP_ADDR', b'example.com'),
            (b'APACHE_PORT_80_TCP_PORT', b'8080'),
        )
        unit_environment = environment_variables + link_environment_variables
        environment = Environment(variables=frozenset(unit_environment))
        unit1 = UNIT_FOR_APP.set("environment", environment)
        units = {unit1.name: unit1}
        links = [
            Link(local_port=80, remote_port=8080, alias=u"APACHE")
        ]
        applications = [APP.set("links", links).set(
            "environment", dict(environment_variables))]
        self._verify_discover_state_applications(units, applications)

    def test_discover_application_with_links(self):
        """
        An ``Application`` with ``Link`` objects is discovered from a ``Unit``
        with environment variables that correspond to an exposed link.
        """
        applications = [APP.set("links", [
            Link(local_port=80, remote_port=8080, alias=u'APACHE')
        ])]
        self._verify_discover_state_applications(
            {}, applications, start_applications=True)

    def test_discover_application_with_ports(self):
        """
        An ``Application`` with ``Port`` objects is discovered from a ``Unit``
        with exposed ``Portmap`` objects.
        """
        ports = [PortMap(internal_port=80, external_port=8080)]
        unit1 = UNIT_FOR_APP.set("ports", ports)
        units = {unit1.name: unit1}
        applications = [APP.set("ports",
                                [Port(internal_port=80, external_port=8080)])]

        self._verify_discover_state_applications(units, applications)

    def test_discover_attached_volume(self):
        """
        Datasets that are mounted at a path that matches the container's
        volume are added to ``Application`` with same name as an
        ``AttachedVolume``.
        """
        DATASET_ID = unicode(uuid4())
        DATASET_ID2 = unicode(uuid4())

        path1 = FilePath(b"/flocker").child(DATASET_ID.encode("ascii"))
        path2 = FilePath(b"/flocker").child(DATASET_ID2.encode("ascii"))
        manifestations = {dataset_id:
                          Manifestation(
                              dataset=Dataset(dataset_id=dataset_id),
                              primary=True,
                          )
                          for dataset_id in (DATASET_ID, DATASET_ID2)}
        current_known_state = NodeState(uuid=self.node_uuid,
                                        hostname=u'example.com',
                                        manifestations=manifestations,
                                        devices={},
                                        paths={DATASET_ID: path1,
                                               DATASET_ID2: path2})

        unit1 = UNIT_FOR_APP.set("volumes", [
            DockerVolume(
                node_path=path1,
                container_path=FilePath(b'/var/lib/data')
            )]
        )

        unit2 = UNIT_FOR_APP2.set("volumes", [
            DockerVolume(
                node_path=path2,
                container_path=FilePath(b'/var/lib/data')
            )]
        )
        units = {unit1.name: unit1, unit2.name: unit2}
        applications = [app.set("volume", AttachedVolume(
            manifestation=manifestations[respective_id],
            mountpoint=FilePath(b'/var/lib/data')
        )) for (app, respective_id) in [(APP, DATASET_ID),
                                        (APP2, DATASET_ID2)]]
        self._verify_discover_state_applications(
            units, applications, current_state=current_known_state)

    def test_ignore_unknown_volumes(self):
        """
        Docker volumes that cannot be matched to a dataset are ignored.
        """
        unit = UNIT_FOR_APP.set("volumes", [
            DockerVolume(
                node_path=FilePath(b"/some/random/path"),
                container_path=FilePath(b'/var/lib/data')
            )],
        )
        units = {unit.name: unit}
        applications = [APP]
        self._verify_discover_state_applications(units, applications)

    def test_not_running_units(self):
        """
        Units that are not active are considered to be not running by
        ``discover_state()``.
        """
        unit1 = UNIT_FOR_APP.set("activation_state", u"inactive")
        unit2 = UNIT_FOR_APP2.set("activation_state", u'madeup')
        units = {unit1.name: unit1, unit2.name: unit2}
        applications = [APP.set("running", False), APP2.set("running", False)]
        self._verify_discover_state_applications(units, applications)

    def test_discover_application_restart_policy(self):
        """
        An ``Application`` with the appropriate ``IRestartPolicy`` is
        discovered from the corresponding restart policy of the ``Unit``.
        """
        policy = RestartAlways()
        unit1 = UNIT_FOR_APP.set("restart_policy", policy)
        units = {unit1.name: unit1}
        applications = [APP.set("restart_policy", policy)]
        self._verify_discover_state_applications(units, applications)

    def test_unknown_manifestations(self):
        """
        If the given ``NodeState`` indicates ignorance of manifestations, the
        ``ApplicationNodeDeployer`` doesn't bother doing any discovery and
        just indicates ignorance of applications.
        """
        units = {APP_NAME: UNIT_FOR_APP}
        applications = None
        # Apparently we know nothing about manifestations one way or the
        # other:
        current_state = NodeState(
            uuid=self.node_uuid,
            hostname=self.hostname,
            manifestations=None, paths=None)
        self._verify_discover_state_applications(
            units, applications, current_state=current_state)


def restart(old, new, node_state):
    """
    Construct the exact ``IStateChange`` that ``ApplicationNodeDeployer``
    returns when it wants to restart a particular application on a particular
    node.
    """
    return sequentially(changes=[
        in_parallel(changes=[
            sequentially(changes=[
                StopApplication(application=old),
                StartApplication(
                    application=new, node_state=node_state,
                ),
            ]),
        ]),
    ])


def no_change():
    """
    Construct the exact ``IStateChange`` that ``ApplicationNodeDeployer``
    returns when it doesn't want to make any changes.
    """
    return NoOp(sleep=NOOP_SLEEP_TIME)


class ApplicationNodeDeployerCalculateVolumeChangesTests(TestCase):
    """
    Tests for ``ApplicationNodeDeployer.calculate_changes`` specifically as it
    relates to volume state and configuration.
    """
    def test_no_volume_no_changes(self):
        """
        If an ``Application`` with no volume is configured and exists, no
        changes are calculated.
        """
        local_state = EMPTY_NODESTATE.set(
            applications=[APPLICATION_WITHOUT_VOLUME],
        )
        local_config = to_node(local_state)
        assert_application_calculated_changes(
            self, local_state, local_config, set(), no_change(),
        )

    def test_has_volume_no_changes(self):
        """
        If an ``Application`` with a volume (with a maximum size) is configured
        and exists with that configuration, no changes are calculated.
        """
        application = APPLICATION_WITH_VOLUME_SIZE
        manifestation = application.volume.manifestation
        local_state = EMPTY_NODESTATE.set(
            devices={UUID(manifestation.dataset_id): FilePath(b"/dev/foo")},
            paths={manifestation.dataset_id: FilePath(b"/foo/bar")},
            manifestations={manifestation.dataset_id: manifestation},
            applications=[application],
        )
        local_config = to_node(local_state)
        assert_application_calculated_changes(
            self, local_state, local_config, set(), no_change(),
        )

    def test_has_volume_cant_change_yet(self):
        """
        If an ``Application`` is configured with a volume but exists without it
        and the dataset for the volume isn't present on the node, no changes
        are calculated.
        """
        application = APPLICATION_WITH_VOLUME_SIZE
        manifestation = application.volume.manifestation
        local_state = EMPTY_NODESTATE.set(
            applications=[application.set("volume", None)],
        )
        local_config = to_node(local_state).set(
            manifestations={manifestation.dataset_id: manifestation},
            applications=[application],
        )
        assert_application_calculated_changes(
            self, local_state, local_config, set(), no_change(),
        )

    def test_has_volume_needs_changes(self):
        """
        If an ``Application`` is configured with a volume but exists without
        the volume and the dataset for the volume is present on the node, a
        change to restart that application is calculated.
        """
        application = APPLICATION_WITH_VOLUME_SIZE
        application_without_volume = application.set(volume=None)
        manifestation = application.volume.manifestation
        local_state = EMPTY_NODESTATE.set(
            devices={UUID(manifestation.dataset_id): FilePath(b"/dev/foo")},
            paths={manifestation.dataset_id: FilePath(b"/foo/bar")},
            manifestations={manifestation.dataset_id: manifestation},
            applications=[application_without_volume],
        )
        local_config = to_node(local_state).set(
            applications=[application],
        )
        assert_application_calculated_changes(
            self, local_state, local_config, set(),
            restart(application_without_volume, application, local_state),
        )

    def test_no_volume_needs_changes(self):
        """
        If an ``Application`` is configured with no volume but exists with one,
        a change to restart that application is calculated.
        """
        application = APPLICATION_WITH_VOLUME_SIZE
        application_without_volume = application.set(volume=None)
        manifestation = application.volume.manifestation
        local_state = EMPTY_NODESTATE.set(
            devices={UUID(manifestation.dataset_id): FilePath(b"/dev/foo")},
            paths={manifestation.dataset_id: FilePath(b"/foo/bar")},
            manifestations={manifestation.dataset_id: manifestation},
            applications=[application],
        )
        local_config = to_node(local_state).set(
            applications=[application_without_volume],
        )
        assert_application_calculated_changes(
            self, local_state, local_config, set(),
            restart(application, application_without_volume, local_state),
        )

    def _resize_no_changes(self, state_size, config_size):
        application_state = APPLICATION_WITH_VOLUME.transform(
            ["volume", "manifestation", "dataset", "maximum_size"],
            state_size,
        )
        application_config = application_state.transform(
            ["volume", "manifestation", "dataset", "maximum_size"],
            config_size,
        )
        manifestation_state = application_state.volume.manifestation
        manifestation_config = application_config.volume.manifestation

        # Both objects represent the same dataset so the id is the same on
        # each.
        dataset_id = manifestation_state.dataset_id

        local_state = EMPTY_NODESTATE.set(
            devices={UUID(dataset_id): FilePath(b"/dev/foo")},
            paths={dataset_id: FilePath(b"/foo/bar")},
            manifestations={dataset_id: manifestation_state},
            applications=[application_state],
        )
        local_config = to_node(local_state).set(
            applications=[application_config],
            manifestations={dataset_id: manifestation_config},
        )
        assert_application_calculated_changes(
            self, local_state, local_config, set(), no_change(),
        )

    def test_resized_volume_no_changes(self):
        """
        If an ``Application`` is configured with a volume and exists with that
        volume but the volume is a different size than configured, no changes
        are calculated because ``ApplicationNodeDeployer`` doesn't trust the
        dataset agent to be able to resize volumes.
        """
        self._resize_no_changes(GiB(1).to_Byte().value, GiB(2).to_Byte().value)

    def test_maximum_volume_size_applied_no_changes(self):
        """
        If an ``Application``\ 's volume exists without a maximum size and the
        configuration for that volume indicates a size, no changes are
        calculated because ``ApplicationNodeDeployer`` doesn't trust the
        dataset agent to be able to resize volumes.
        """
        self._resize_no_changes(None, GiB(1).to_Byte().value)

    def test_maximum_volume_size_removed_no_changes(self):
        """
        If an ``Application``\ 's volume exists with a maximum size and the
        configuration for that volume indicates no maximum size, no changes are
        calculated because ``ApplicationNodeDeployer`` doesn't trust the
        dataset agent to be able to resize volumes.
        """
        self._resize_no_changes(GiB(1).to_Byte().value, None)

    def test_moved_volume_needs_changes(self):
        """
        If an ``Application`` is configured with a volume on a node but is no
        longer configured to on that node, a change to stop that application is
        calculated.
        """
        application = APPLICATION_WITH_VOLUME_SIZE
        manifestation = application.volume.manifestation
        local_state = EMPTY_NODESTATE.set(
            devices={UUID(manifestation.dataset_id): FilePath(b"/dev/foo")},
            paths={manifestation.dataset_id: FilePath(b"/foo/bar")},
            manifestations={manifestation.dataset_id: manifestation},
            applications=[application],
        )
        local_config = to_node(EMPTY_NODESTATE)
        assert_application_calculated_changes(
            self, local_state, local_config, set(),
            sequentially(changes=[
                in_parallel(changes=[
                    StopApplication(application=application),
                ]),
            ]),
        )

    def test_different_volume_needs_change(self):
        """
        If an ``Application`` is configured with a volume but exists with a
        different volume, a change to restart that application is calculated.
        """
        application = APPLICATION_WITH_VOLUME_SIZE
        manifestation = application.volume.manifestation
        another_manifestation = manifestation.transform(
            ["dataset", "dataset_id"], uuid4(),
        )
        changed_application = application.transform(
            ["volume", "manifestation"], another_manifestation,
        )
        local_state = EMPTY_NODESTATE.set(
            devices={
                UUID(manifestation.dataset_id): FilePath(b"/dev/foo"),
                UUID(another_manifestation.dataset_id): FilePath(b"/dev/bar"),
            },
            paths={
                manifestation.dataset_id: FilePath(b"/foo/bar"),
                another_manifestation.dataset_id: FilePath(b"/bar/baz"),
            },
            manifestations={
                manifestation.dataset_id: manifestation,
                another_manifestation.dataset_id: another_manifestation,
            },
            applications=[application],
        )
        local_config = to_node(local_state).set(
            applications=[
                changed_application,
            ],
        )
        assert_application_calculated_changes(
            self, local_state, local_config, set(),
            restart(application, changed_application, local_state),
        )


class ApplicationNodeDeployerCalculateChangesTests(TestCase):
    """
    Tests for ``ApplicationNodeDeployer.calculate_changes``.
    """
    def test_no_state_changes(self):
        """
        ``ApplicationNodeDeployer.calculate_changes`` returns a
        ``Deferred`` which fires with a :class:`IStateChange` instance
        indicating that no changes are necessary when there are no
        applications running or desired, and no proxies exist or are
        desired.
        """
        assert_application_calculated_changes(
            self, EMPTY_NODESTATE, to_node(EMPTY_NODESTATE), set(),
            no_change(),
        )

    def test_proxy_needs_creating(self):
        """
        ``ApplicationNodeDeployer.calculate_changes`` returns a
        ``IStateChange``, specifically a ``SetProxies`` with a list of
        ``Proxy`` objects. One for each port exposed by ``Application``\ s
        hosted on a remote nodes.
        """
        port = Port(
            internal_port=3306, external_port=1001,
        )
        application = Application(
            name=u'mysql-hybridcluster',
            image=DockerImage(repository=u'clusterhq/mysql',
                              tag=u'release-14.0'),
            ports=frozenset([port]),
        )
        local_state = NodeState(
            uuid=uuid4(), hostname=u"192.0.2.100",
            applications=[],
            manifestations={}, devices={}, paths={},
        )
        destination_state = NodeState(
            uuid=uuid4(), hostname=u"192.0.2.101",
            applications=[application],
            manifestations={}, devices={}, paths={},
        )
        local_config = to_node(local_state)

        proxy = Proxy(
            ip=destination_state.hostname,
            port=port.external_port,
        )
        expected = sequentially(changes=[SetProxies(ports=frozenset([proxy]))])
        assert_application_calculated_changes(
            self, local_state, local_config, set(),
            additional_node_states={destination_state},
            additional_node_config={to_node(destination_state)},
            expected_changes=expected,
        )

    def test_no_proxy_if_node_state_unknown(self):
        """
        ``ApplicationNodeDeployer.calculate_changes`` does not attempt to
        create a proxy to a node whose state is unknown, since the
        destination IP is unavailable.
        """
        api = ApplicationNodeDeployer(u'192.168.1.1', node_uuid=uuid4(),
                                      docker_client=FakeDockerClient(),
                                      network=make_memory_network())
        expected_destination_port = 1001
        port = Port(internal_port=3306,
                    external_port=expected_destination_port)
        application = Application(
            name=u'mysql-hybridcluster',
            image=DockerImage(repository=u'clusterhq/mysql',
                              tag=u'release-14.0'),
            ports=frozenset([port]),
        )
        desired = Deployment(nodes=[Node(uuid=uuid4(),
                                         applications=[application])])
        result = api.calculate_changes(
            desired_configuration=desired, current_cluster_state=EMPTY_STATE,
            local_state=empty_node_local_state(api))
        expected = sequentially(changes=[])
        self.assertEqual(expected, result)

    def test_proxy_empty(self):
        """
        ``ApplicationNodeDeployer.calculate_changes`` returns a
        ``SetProxies`` instance containing an empty `proxies`
        list if there are no remote applications that need proxies.
        """
        network = make_memory_network()
        network.create_proxy_to(ip=u'192.0.2.100', port=3306)

        api = ApplicationNodeDeployer(u'node2.example.com',
                                      docker_client=FakeDockerClient(),
                                      network=network)
        desired = Deployment(nodes=frozenset())
        result = api.calculate_changes(
            desired_configuration=desired, current_cluster_state=EMPTY,
            local_state=empty_node_local_state(api))
        expected = sequentially(changes=[SetProxies(ports=frozenset())])
        self.assertEqual(expected, result)

    def test_open_port_needs_creating(self):
        """
        ``ApplicationNodeDeployer.calculate_changes`` returns a
        ``IStateChange``, specifically a ``OpenPorts`` with a list of
        ports to open. One for each port exposed by ``Application``\ s
        hosted on this node.
        """
        api = ApplicationNodeDeployer(u'example.com',
                                      docker_client=FakeDockerClient(),
                                      network=make_memory_network(),
                                      node_uuid=uuid4())
        expected_destination_port = 1001
        port = Port(internal_port=3306,
                    external_port=expected_destination_port)
        application = Application(
            name=u'mysql-hybridcluster',
            image=DockerImage(repository=u'clusterhq/mysql',
                              tag=u'release-14.0'),
            ports=[port],
        )

        nodes = [
            Node(
                uuid=api.node_uuid,
                applications=[application]
            )
        ]

        node_state = NodeState(
            hostname=api.hostname, uuid=api.node_uuid,
            applications=[])
        desired = Deployment(nodes=nodes)
        result = api.calculate_changes(
            desired_configuration=desired,
            current_cluster_state=DeploymentState(nodes=[node_state]),
            local_state=NodeLocalState(node_state=node_state))
        expected = sequentially(changes=[
            OpenPorts(ports=[OpenPort(port=expected_destination_port)]),
            in_parallel(changes=[
                StartApplication(application=application,
                                 node_state=node_state)])])
        self.assertEqual(expected, result)

    def test_open_ports_empty(self):
        """
        ``ApplicationNodeDeployer.calculate_changes`` returns a
        ``OpenPorts`` instance containing an empty `ports`
        list if there are no local applications that need open_ports.
        """
        network = make_memory_network()
        network.open_port(port=3306)

        api = ApplicationNodeDeployer(u'node2.example.com',
                                      docker_client=FakeDockerClient(),
                                      network=network)
        desired = Deployment(nodes=[])
        result = api.calculate_changes(
            desired_configuration=desired, current_cluster_state=EMPTY,
            local_state=empty_node_local_state(api))
        expected = sequentially(changes=[OpenPorts(ports=[])])
        self.assertEqual(expected, result)

    def test_application_needs_stopping(self):
        """
        ``ApplicationNodeDeployer.calculate_changes`` specifies that an
        application must be stopped when it is running but not desired.
        """
        api = ApplicationNodeDeployer(u'node.example.com',
                                      docker_client=FakeDockerClient(),
                                      network=make_memory_network())

        to_stop = StopApplication(application=Application(
            name=u"site-example.com", image=DockerImage.from_string(
                u"flocker/wordpress")))

        node_state = NodeState(
            hostname=api.hostname, applications={to_stop.application},
        )
        result = api.calculate_changes(
            desired_configuration=EMPTY,
            current_cluster_state=DeploymentState(nodes=[node_state]),
            local_state=NodeLocalState(node_state=node_state))
        expected = sequentially(changes=[in_parallel(changes=[to_stop])])
        self.assertEqual(expected, result)

    def test_application_needs_starting(self):
        """
        ``ApplicationNodeDeployer.calculate_changes`` specifies that an
        application must be started when it is desired on the given node but
        not running.
        """
        api = ApplicationNodeDeployer(u'example.com',
                                      docker_client=FakeDockerClient(),
                                      network=make_memory_network(),
                                      node_uuid=uuid4())
        application = Application(
            name=u'mysql-hybridcluster',
            image=DockerImage(repository=u'clusterhq/flocker',
                              tag=u'release-14.0')
        )

        nodes = frozenset([
            Node(
                uuid=api.node_uuid,
                applications=frozenset([application])
            )
        ])

        node_state = NodeState(
            hostname=api.hostname, uuid=api.node_uuid,
            applications=[])

        desired = Deployment(nodes=nodes)
        result = api.calculate_changes(
            desired_configuration=desired,
            current_cluster_state=DeploymentState(nodes=[node_state]),
            local_state=NodeLocalState(node_state=node_state))
        expected = sequentially(changes=[in_parallel(
            changes=[StartApplication(application=application,
                                      node_state=node_state)])])
        self.assertEqual(expected, result)

    def test_only_this_node(self):
        """
        ``ApplicationNodeDeployer.calculate_changes`` does not specify
        that an application must be started if the desired changes apply
        to a different node.
        """
        api = ApplicationNodeDeployer(u'node.example.com',
                                      docker_client=FakeDockerClient(),
                                      network=make_memory_network())
        application = Application(
            name=u'mysql-hybridcluster',
            image=DockerImage(repository=u'clusterhq/flocker',
                              tag=u'release-14.0')
        )

        nodes = frozenset([
            Node(
                hostname=u'node1.example.net',
                applications=frozenset([application])
            )
        ])

        desired = Deployment(nodes=nodes)
        result = api.calculate_changes(
            desired_configuration=desired,
            current_cluster_state=EMPTY_STATE,
            local_state=empty_node_local_state(api))
        expected = sequentially(changes=[])
        self.assertEqual(expected, result)

    def test_no_change_needed(self):
        """
        ``ApplicationNodeDeployer.calculate_changes`` does not specify
        that an application must be started or stopped if the desired
        configuration is the same as the current configuration.
        """
        api = ApplicationNodeDeployer(u'node.example.com',
                                      docker_client=FakeDockerClient(),
                                      network=make_memory_network())

        application = Application(
            name=u'mysql-hybridcluster',
            image=DockerImage(repository=u'clusterhq/mysql',
                              tag=u'latest'),
            ports=frozenset(),
        )

        nodes = frozenset([
            Node(
                hostname=u'node.example.com',
                applications=frozenset([application])
            )
        ])

        desired = Deployment(nodes=nodes)
        node_state = NodeState(hostname=api.hostname,
                               applications=[application])
        result = api.calculate_changes(
            desired_configuration=desired,
            current_cluster_state=DeploymentState(nodes=[node_state]),
            local_state=NodeLocalState(node_state=node_state))
        expected = no_change()
        self.assertEqual(expected, result)

    def test_node_not_described(self):
        """
        ``ApplicationNodeDeployer.calculate_changes`` specifies that
        all applications on a node must be stopped if the desired
        configuration does not include that node.
        """
        api = ApplicationNodeDeployer(u'node.example.com',
                                      docker_client=FakeDockerClient(),
                                      network=make_memory_network())
        application = Application(
            name=u"my-db",
            image=DockerImage.from_string("postgres")
        )
        desired = Deployment(nodes=frozenset())
        node_state = NodeState(hostname=api.hostname,
                               applications=[application])
        result = api.calculate_changes(
            desired_configuration=desired,
            current_cluster_state=DeploymentState(nodes=[node_state]),
            local_state=NodeLocalState(node_state=node_state))
        to_stop = StopApplication(
            application=application,
        )
        expected = sequentially(changes=[in_parallel(changes=[to_stop])])
        self.assertEqual(expected, result)

    def test_local_not_running_applications_restarted(self):
        """
        Applications that are not running but are supposed to be on the local
        node are restarted by Flocker (we cannot rely on Docker restart
        policies to do so because FLOC-3148).
        """
        api = ApplicationNodeDeployer(u'n.example.com',
                                      docker_client=FakeDockerClient(),
                                      network=make_memory_network(),
                                      node_uuid=uuid4())
        application_desired = Application(
            name=u'mysql-hybridcluster',
            image=DockerImage(repository=u'clusterhq/flocker',
                              tag=u'release-14.0'),
        )
        application_stopped = application_desired.set("running", False)
        nodes_desired = frozenset([
            Node(
                uuid=api.node_uuid,
                applications=frozenset([application_desired])
            )
        ])
        node_state = NodeState(
            hostname=api.hostname,
            uuid=api.node_uuid,
            applications=[application_stopped])
        desired = Deployment(nodes=nodes_desired)
        result = api.calculate_changes(
            desired_configuration=desired,
            current_cluster_state=DeploymentState(nodes=[node_state]),
            local_state=NodeLocalState(node_state=node_state))

        expected = sequentially(changes=[in_parallel(changes=[
            sequentially(changes=[
                StopApplication(application=application_stopped),
                StartApplication(
                    application=application_desired, node_state=node_state),
            ])])])
        self.assertEqual(expected, result)

    def test_not_local_not_running_applications_stopped(self):
        """
        Applications that are not running and are not supposed to be on the
        local node are added to the list of applications to stop.
        """
        api = ApplicationNodeDeployer(
            u'example.com',
            docker_client=FakeDockerClient(),
            network=make_memory_network())
        to_stop = Application(
            name=u"myapp",
            image=DockerImage.from_string(u"postgres"),
            running=False,
        )
        node_state = NodeState(hostname=api.hostname, applications={to_stop})
        result = api.calculate_changes(
            desired_configuration=EMPTY,
            current_cluster_state=DeploymentState(nodes=[node_state]),
            local_state=NodeLocalState(node_state=node_state))
        expected = sequentially(changes=[in_parallel(changes=[
            StopApplication(application=to_stop)])])
        self.assertEqual(expected, result)

    def test_app_with_changed_image_restarted(self):
        """
        An ``Application`` running on a given node that has a different image
        specified in the desired state to the image used by the application now
        is added to the list of applications to restart.
        """
        api = ApplicationNodeDeployer(
            u'node1.example.com',
            docker_client=FakeDockerClient(),
            network=make_memory_network(),
            node_uuid=uuid4(),
        )

        old_postgres_app = Application(
            name=u'postgres-example',
            image=DockerImage.from_string(u'clusterhq/postgres:latest'),
            volume=None
        )

        new_postgres_app = Application(
            name=u'postgres-example',
            image=DockerImage.from_string(u'docker/postgres:latest'),
            volume=None
        )

        desired = Deployment(nodes=frozenset({
            Node(uuid=api.node_uuid,
                 applications=frozenset({new_postgres_app})),
        }))
        node_state = NodeState(
            uuid=api.node_uuid,
            hostname=api.hostname,
            applications={old_postgres_app})
        result = api.calculate_changes(
            desired_configuration=desired,
            current_cluster_state=DeploymentState(nodes={node_state}),
            local_state=NodeLocalState(node_state=node_state)
        )

        expected = sequentially(changes=[in_parallel(changes=[
            sequentially(changes=[
                StopApplication(application=old_postgres_app),
                StartApplication(application=new_postgres_app,
                                 node_state=node_state)
                ]),
        ])])

        self.assertEqual(expected, result)

    def test_app_with_changed_ports_restarted(self):
        """
        An ``Application`` running on a given node that has different port
        exposures specified in the desired state to the ports exposed by the
        application's current state is added to the list of applications to
        restart.
        """
        network = make_memory_network()
        network.open_port(50432)

        api = ApplicationNodeDeployer(
            u'node1.example.com',
            docker_client=FakeDockerClient(),
            network=network,
        )

        old_postgres_app = Application(
            name=u'postgres-example',
            image=DockerImage.from_string(u'clusterhq/postgres:latest'),
            volume=None,
            ports=frozenset([Port(
                internal_port=5432,
                external_port=50432
            )])
        )

        new_postgres_app = Application(
            name=u'postgres-example',
            image=DockerImage.from_string(u'clusterhq/postgres:latest'),
            volume=None,
            ports=frozenset([Port(
                internal_port=5433,
                external_port=50433
            )])
        )

        node_state = NodeState(
            hostname=api.hostname,
            applications={old_postgres_app},
        )

        desired = Deployment(nodes=frozenset({
            Node(hostname=api.hostname,
                 applications=frozenset({new_postgres_app})),
        }))
        result = api.calculate_changes(
            desired_configuration=desired,
            current_cluster_state=DeploymentState(nodes={node_state}),
            local_state=NodeLocalState(node_state=node_state),
        )

        expected = sequentially(changes=[
            OpenPorts(ports=[OpenPort(port=50433)]),
            in_parallel(changes=[
                sequentially(changes=[
                    StopApplication(application=old_postgres_app),
                    StartApplication(application=new_postgres_app,
                                     node_state=node_state)
                ]),
            ]),
        ])

        self.assertEqual(expected, result)

    def test_app_with_changed_links_restarted(self):
        """
        An ``Application`` running on a given node that has different links
        specified in the desired state to the links specified by the
        application's current state is added to the list of applications to
        restart.
        """
        api = ApplicationNodeDeployer(
            u'node1.example.com',
            docker_client=FakeDockerClient(),
            network=make_memory_network()
        )

        old_wordpress_app = Application(
            name=u'wordpress-example',
            image=DockerImage.from_string(u'clusterhq/wordpress:latest'),
            volume=None,
            links=frozenset([
                Link(
                    local_port=5432, remote_port=50432, alias='POSTGRES'
                )
            ])
        )

        postgres_app = Application(
            name=u'postgres-example',
            image=DockerImage.from_string(u'clusterhq/postgres:latest')
        )
        new_wordpress_app = Application(
            name=u'wordpress-example',
            image=DockerImage.from_string(u'clusterhq/wordpress:latest'),
            volume=None,
            links=frozenset([
                Link(
                    local_port=5432, remote_port=51432, alias='POSTGRES'
                )
            ])
        )

        desired = Deployment(nodes=frozenset({
            Node(hostname=u'node1.example.com',
                 applications=frozenset({new_wordpress_app, postgres_app})),
        }))
        node_state = NodeState(hostname=api.hostname,
                               applications={postgres_app, old_wordpress_app})
        result = api.calculate_changes(
            desired_configuration=desired,
            current_cluster_state=DeploymentState(nodes={node_state}),
            local_state=NodeLocalState(node_state=node_state),
        )

        expected = sequentially(changes=[in_parallel(changes=[
            sequentially(changes=[
                StopApplication(application=old_wordpress_app),
                StartApplication(application=new_wordpress_app,
                                 node_state=node_state)
                ]),
        ])])

        self.assertEqual(expected, result)

    def test_stopped_app_with_change_restarted(self):
        """
        An ``Application`` that is stopped, and then reconfigured such that it
        would be restarted if it was running, will be restarted with the
        new configuration.
        """
        api = ApplicationNodeDeployer(
            u'node1.example.com',
            docker_client=FakeDockerClient(),
            network=make_memory_network(),
            node_uuid=uuid4(),
        )

        old_postgres_app = Application(
            name=u'postgres-example',
            image=DockerImage.from_string(u'clusterhq/postgres:latest'),
            running=False,
        )

        new_postgres_app = old_postgres_app.transform(
            ["image"], DockerImage.from_string(u'docker/postgres:latest'),
            ["running"], True)

        desired = Deployment(nodes=[
            Node(uuid=api.node_uuid, applications={new_postgres_app})])
        node_state = NodeState(
            uuid=api.node_uuid,
            hostname=api.hostname,
            applications={old_postgres_app})
        result = api.calculate_changes(
            desired_configuration=desired,
            current_cluster_state=DeploymentState(nodes={node_state}),
            local_state=NodeLocalState(node_state=node_state),
        )

        expected = sequentially(changes=[in_parallel(changes=[
            sequentially(changes=[
                StopApplication(application=old_postgres_app),
                StartApplication(application=new_postgres_app,
                                 node_state=node_state)
                ]),
        ])])

        self.assertEqual(expected, result)

    def test_unknown_applications(self):
        """
        If application state for local state is unknown, don't do anything.
        """
        api = ApplicationNodeDeployer(
            u'node1.example.com',
            docker_client=FakeDockerClient(),
            network=make_memory_network()
        )

        postgres_app = Application(
            name=u'postgres-example',
            image=DockerImage.from_string(u'docker/postgres:latest'),
        )
        node = Node(
            hostname=api.hostname, applications={postgres_app})
        desired = Deployment(nodes=[node])

        node_state = NodeState(hostname=api.hostname, applications=None)
        result = api.calculate_changes(desired, DeploymentState(
            nodes=[node_state]),
            local_state=NodeLocalState(node_state=node_state),
        )
        self.assertEqual(result, sequentially(changes=[]))

    def test_missing_volume(self):
        """
        If a desired but non-running application has a volume but its
        manifestation does not exist on the node, the application is not
        started.

        Eventually the manifestation will appear, at which point the
        application can be started.
        """
        api = ApplicationNodeDeployer(u'example.com',
                                      docker_client=FakeDockerClient(),
                                      network=make_memory_network())
        manifestation = Manifestation(
            dataset=Dataset(dataset_id=unicode(uuid4())),
            primary=True,
        )
        application = Application(
            name=u'mysql-hybridcluster',
            image=DockerImage(repository=u'clusterhq/flocker',
                              tag=u'release-14.0'),
            volume=AttachedVolume(
                manifestation=manifestation,
                mountpoint=FilePath(b"/data"),
            )
        )

        desired = Deployment(
            nodes=[Node(hostname=api.hostname, applications=[application],
                        manifestations={manifestation.dataset_id:
                                        manifestation})])

        result = api.calculate_changes(
            desired_configuration=desired,
            # No manifestations available!
            current_cluster_state=EMPTY_STATE,
            local_state=empty_node_local_state(api),
        )
        expected = sequentially(changes=[])
        self.assertEqual(expected, result)

    def _app_restart_policy_test(self, restart_state, restart_config,
                                 expect_restart):
        """
        Verify that an application with a particular restart policy in its
        state and in another (or the same) policy in its configuration is
        either restarted or not.

        :param IRestartPolicy restart_state: The policy to put into the
            application state.
        :param IRestartPolicy restart_config: The policy to put into the
            application configuration.
        :param bool expect_restart: ``True`` if the given combination must
            provoke an application restart.  ``False`` if it must not.

        :raise: A test-failing exception if the restart expection is not met.
        """
        app_state = APPLICATION_WITHOUT_VOLUME.set(
            restart_policy=restart_state,
        )
        node_state = NodeState(
            uuid=uuid4(), hostname=u"192.0.2.10",
            applications={app_state},
        )
        app_config = app_state.set(
            restart_policy=restart_config,
        )
        node_config = to_node(node_state.set(applications={app_config}))
        if expect_restart:
            expected_changes = restart(app_state, app_config, node_state)
        else:
            expected_changes = no_change()
        assert_application_calculated_changes(
            self, node_state, node_config, set(),
            expected_changes,
        )

    def test_app_state_always_and_config_always_restarted(self):
        """
        Restart policies interact poorly with containers with volumes.  If an
        application state is found with a restart policy other than "never",
        even if the application configuration matches that restart policy, it
        is restarted with the "never" policy.  See FLOC-2449.
        """
        self._app_restart_policy_test(RestartAlways(), RestartAlways(), True)

    def test_app_state_always_and_config_failure_restarted(self):
        """
        See ``test_app_state_always_and_config_always_restarted``
        """
        self._app_restart_policy_test(
            RestartAlways(), RestartOnFailure(maximum_retry_count=2), True,
        )

    def test_app_state_always_and_config_never_restarted(self):
        """
        See ``test_app_state_always_and_config_always_restarted``
        """
        self._app_restart_policy_test(RestartAlways(), RestartNever(), True)

    def test_app_state_never_and_config_never_not_restarted(self):
        """
        See ``test_app_state_always_and_config_always_restarted``
        """
        self._app_restart_policy_test(RestartNever(), RestartNever(), False)

    def test_app_state_never_and_config_always_not_restarted(self):
        """
        See ``test_app_state_always_and_config_always_restarted``
        """
        self._app_restart_policy_test(RestartNever(), RestartAlways(), False)

    def test_app_state_never_and_config_failure_not_restarted(self):
        """
        See ``test_app_state_always_and_config_always_restarted``
        """
        self._app_restart_policy_test(
            RestartNever(), RestartOnFailure(maximum_retry_count=2), False,
        )

    def test_app_state_failure_and_config_never_restarted(self):
        """
        See ``test_app_state_always_and_config_always_restarted``
        """
        self._app_restart_policy_test(
            RestartOnFailure(maximum_retry_count=2), RestartNever(), True,
        )

    def test_app_state_failure_and_config_always_restarted(self):
        """
        See ``test_app_state_always_and_config_always_restarted``
        """
        self._app_restart_policy_test(
            RestartOnFailure(maximum_retry_count=2), RestartAlways(), True,
        )

    def test_app_state_failure_and_config_failure_restarted(self):
        """
        See ``test_app_state_always_and_config_always_restarted``
        """
        self._app_restart_policy_test(
            RestartOnFailure(maximum_retry_count=2),
            RestartOnFailure(maximum_retry_count=2),
            True,
        )


class SetProxiesTests(TestCase):
    """
    Tests for ``SetProxies``.
    """
    def test_proxies_added(self):
        """
        Proxies which are required are added.
        """
        fake_network = make_memory_network()
        api = ApplicationNodeDeployer(
            u'example.com',
            docker_client=FakeDockerClient(),
            network=fake_network)

        expected_proxy = Proxy(ip=u'192.0.2.100', port=3306)
        d = SetProxies(ports=[expected_proxy]).run(
            api, state_persister=InMemoryStatePersister())
        self.successResultOf(d)
        self.assertEqual(
            [expected_proxy],
            fake_network.enumerate_proxies()
        )

    def test_proxies_removed(self):
        """
        Proxies which are no longer required on the node are removed.
        """
        fake_network = make_memory_network()
        fake_network.create_proxy_to(ip=u'192.0.2.100', port=3306)
        api = ApplicationNodeDeployer(
            u'example.com', docker_client=FakeDockerClient(),
            network=fake_network)

        d = SetProxies(ports=[]).run(
            api, state_persister=InMemoryStatePersister())
        self.successResultOf(d)
        self.assertEqual(
            [],
            fake_network.enumerate_proxies()
        )

    def test_desired_proxies_remain(self):
        """
        Proxies which exist on the node and which are still required are not
        removed.
        """
        fake_network = make_memory_network()

        # A proxy which will be removed
        fake_network.create_proxy_to(ip=u'192.0.2.100', port=3306)
        # And some proxies which are still required
        required_proxy1 = fake_network.create_proxy_to(ip=u'192.0.2.101',
                                                       port=3306)
        required_proxy2 = fake_network.create_proxy_to(ip=u'192.0.2.101',
                                                       port=8080)

        api = ApplicationNodeDeployer(
            u'example.com', docker_client=FakeDockerClient(),
            network=fake_network)

        d = SetProxies(ports=[required_proxy1, required_proxy2]).run(
            api, state_persister=InMemoryStatePersister())

        self.successResultOf(d)
        self.assertEqual(
            set([required_proxy1, required_proxy2]),
            set(fake_network.enumerate_proxies())
        )

    @capture_logging(None)
    def test_delete_proxy_errors_as_errbacks(self, logger):
        """
        Exceptions raised in `delete_proxy` operations are reported as
        failures in the returned deferred.
        """
        fake_network = make_memory_network()
        fake_network.create_proxy_to(ip=u'192.0.2.100', port=3306)
        fake_network.delete_proxy = lambda proxy: 1/0

        api = ApplicationNodeDeployer(
            u'example.com', docker_client=FakeDockerClient(),
            network=fake_network)

        d = SetProxies(ports=[]).run(
            api, state_persister=InMemoryStatePersister())
        exception = self.failureResultOf(d, FirstError)
        self.assertIsInstance(
            exception.value.subFailure.value,
            ZeroDivisionError
        )
        logger.flush_tracebacks(ZeroDivisionError)

    @capture_logging(None)
    def test_create_proxy_errors_as_errbacks(self, logger):
        """
        Exceptions raised in `create_proxy_to` operations are reported as
        failures in the returned deferred.
        """
        fake_network = make_memory_network()
        fake_network.create_proxy_to = lambda ip, port: 1/0

        api = ApplicationNodeDeployer(
            u'example.com', docker_client=FakeDockerClient(),
            network=fake_network)

        d = SetProxies(ports=[Proxy(ip=u'192.0.2.100', port=3306)]).run(
            api, state_persister=InMemoryStatePersister())
        exception = self.failureResultOf(d, FirstError)
        self.assertIsInstance(
            exception.value.subFailure.value,
            ZeroDivisionError
        )
        logger.flush_tracebacks(ZeroDivisionError)

    @capture_logging(None)
    def test_create_proxy_errors_all_logged(self, logger):
        """
        Exceptions raised in `create_proxy_to` operations are all logged.
        """
        fake_network = make_memory_network()
        fake_network.create_proxy_to = lambda ip, port: 1/0

        api = ApplicationNodeDeployer(
            u'example.com', docker_client=FakeDockerClient(),
            network=fake_network)

        d = SetProxies(
            ports=[Proxy(ip=u'192.0.2.100', port=3306),
                   Proxy(ip=u'192.0.2.101', port=3306),
                   Proxy(ip=u'192.0.2.102', port=3306)]
        ).run(api, state_persister=InMemoryStatePersister())

        self.failureResultOf(d, FirstError)

        failures = logger.flush_tracebacks(ZeroDivisionError)
        self.assertEqual(3, len(failures))


class OpenPortsTests(TestCase):
    """
    Tests for ``OpenPorts``.
    """
    def test_open_ports_added(self):
        """
        Porst which are required are opened.
        """
        fake_network = make_memory_network()
        api = ApplicationNodeDeployer(
            u'example.com', docker_client=FakeDockerClient(),
            network=fake_network)

        expected_open_port = OpenPort(port=3306)
        d = OpenPorts(ports=[expected_open_port]).run(
            api, state_persister=InMemoryStatePersister())
        self.successResultOf(d)
        self.assertEqual(
            [expected_open_port],
            fake_network.enumerate_open_ports()
        )

    def test_open_ports_removed(self):
        """
        Open ports which are no longer required on the node are closed.
        """
        fake_network = make_memory_network()
        fake_network.open_port(port=3306)
        api = ApplicationNodeDeployer(
            u'example.com', docker_client=FakeDockerClient(),
            network=fake_network)

        d = OpenPorts(ports=[]).run(
            api, state_persister=InMemoryStatePersister())
        self.successResultOf(d)
        self.assertEqual(
            [],
            fake_network.enumerate_proxies()
        )

    def test_desired_open_ports_remain(self):
        """
        Open ports which exist on the node and which are still required are not
        removed.
        """
        fake_network = make_memory_network()

        # A open_port which will be removed
        fake_network.open_port(port=3305)
        # And some open ports which are still required
        required_open_port_1 = fake_network.open_port(port=3306)
        required_open_port_2 = fake_network.open_port(port=8080)

        api = ApplicationNodeDeployer(
            u'example.com', docker_client=FakeDockerClient(),
            network=fake_network)

        state_change = OpenPorts(
            ports=[required_open_port_1, required_open_port_2])
        d = state_change.run(api, state_persister=InMemoryStatePersister())

        self.successResultOf(d)
        self.assertEqual(
            set([required_open_port_1, required_open_port_2]),
            set(fake_network.enumerate_open_ports())
        )

    @capture_logging(None)
    def test_delete_open_port_errors_as_errbacks(self, logger):
        """
        Exceptions raised in `delete_open_port` operations are reported as
        failures in the returned deferred.
        """
        fake_network = make_memory_network()
        fake_network.open_port(port=3306)
        fake_network.delete_open_port = lambda open_port: 1/0

        api = ApplicationNodeDeployer(
            u'example.com', docker_client=FakeDockerClient(),
            network=fake_network)

        d = OpenPorts(ports=[]).run(
            api, state_persister=InMemoryStatePersister())
        exception = self.failureResultOf(d, FirstError)
        self.assertIsInstance(
            exception.value.subFailure.value,
            ZeroDivisionError
        )
        logger.flush_tracebacks(ZeroDivisionError)

    @capture_logging(None)
    def test_open_port_errors_as_errbacks(self, logger):
        """
        Exceptions raised in `open_port` operations are reported as
        failures in the returned deferred.
        """
        fake_network = make_memory_network()
        fake_network.open_port = lambda port: 1/0

        api = ApplicationNodeDeployer(
            u'example.com', docker_client=FakeDockerClient(),
            network=fake_network)

        d = OpenPorts(ports=[OpenPort(port=3306)]).run(
            api, state_persister=InMemoryStatePersister())
        exception = self.failureResultOf(d, FirstError)
        self.assertIsInstance(
            exception.value.subFailure.value,
            ZeroDivisionError
        )
        logger.flush_tracebacks(ZeroDivisionError)

    @capture_logging(None)
    def test_open_ports_errors_all_logged(self, logger):
        """
        Exceptions raised in `OpenPorts` operations are all logged.
        """
        fake_network = make_memory_network()
        fake_network.open_port = lambda port: 1/0

        api = ApplicationNodeDeployer(
            u'example.com', docker_client=FakeDockerClient(),
            network=fake_network)

        d = OpenPorts(
            ports=[OpenPort(port=3306),
                   OpenPort(port=3307),
                   OpenPort(port=3308)]
        ).run(api, state_persister=InMemoryStatePersister())

        self.failureResultOf(d, FirstError)

        failures = logger.flush_tracebacks(ZeroDivisionError)
        self.assertEqual(3, len(failures))
