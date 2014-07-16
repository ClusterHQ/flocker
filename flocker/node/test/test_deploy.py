# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for ``flocker.node._deploy``.
"""

from uuid import uuid4

from twisted.internet.defer import fail, FirstError
from twisted.trial.unittest import SynchronousTestCase
from twisted.python.filepath import FilePath
from twisted.internet.task import Clock

from .. import (Deployer, Application, DockerImage, Deployment, Node,
                StateChanges, Port)
from .._model import AttachedVolume
from ..gear import GearClient, FakeGearClient, AlreadyExists, Unit, PortMap
from ...route import INetwork
from ...volume.service import VolumeService, Volume
from ...volume.filesystems.memory import FilesystemStoragePool


def create_volume_service(test):
    """
    Create a new ``VolumeService``.

    :param TestCase test: A unit test which will shut down the service
        when done.

    :return: The ``VolumeService`` created.
    """
    service = VolumeService(FilePath(test.mktemp()),
                            FilesystemStoragePool(FilePath(test.mktemp())),
                            reactor=Clock())
    service.startService()
    test.addCleanup(service.stopService)
    return service


class DeployerAttributesTests(SynchronousTestCase):
    """
    Tests for attributes and initialiser arguments of `Deployer`.
    """
    def test_gear_client_default(self):
        """
        ``Deployer._gear_client`` is a ``GearClient`` by default.
        """
        self.assertIsInstance(
            Deployer(None)._gear_client,
            GearClient
        )

    def test_gear_override(self):
        """
        ``Deployer._gear_client`` can be overridden in the constructor.
        """
        dummy_gear_client = object()
        self.assertIs(
            dummy_gear_client,
            Deployer(create_volume_service(self),
                     gear_client=dummy_gear_client)._gear_client
        )

    def test_network_default(self):
        """
        ``Deployer._network`` is an ``INetwork`` by default.
        """
        self.assertTrue(INetwork.providedBy(Deployer(None)._network))

    def test_network_override(self):
        """
        ``Deployer._network`` can be overridden in the constructor.
        """
        dummy_network = object()
        self.assertIs(
            dummy_network,
            Deployer(create_volume_service(self),
                     network=dummy_network)._network
        )


class DeployerStartApplicationTests(SynchronousTestCase):
    """
    Tests for `Deployer.start_application`.
    """
    def test_start(self):
        """
        `Deployer.start_application` accepts an application object and returns
        a `Deferred` which fires when the `gear` unit has been added and
        started.
        """
        fake_gear = FakeGearClient()
        api = Deployer(create_volume_service(self), gear_client=fake_gear)
        docker_image = DockerImage(repository=u'clusterhq/flocker',
                                   tag=u'release-14.0')
        ports = frozenset([Port(internal_port=80, external_port=8080)])
        application = Application(
            name=b'site-example.com',
            image=docker_image,
            ports=ports,
        )
        start_result = api.start_application(application=application)
        exists_result = fake_gear.exists(unit_name=application.name)

        port_maps = [PortMap(internal_port=80, external_port=8080)]
        self.assertEqual(
            (None, True, docker_image.full_name, port_maps),
            (self.successResultOf(start_result),
             self.successResultOf(exists_result),
             fake_gear._units[application.name].container_image,
             fake_gear._units[application.name].ports)
        )

    def test_already_exists(self):
        """
        ``Deployer.start_application`` returns a `Deferred` which errbacks with
        an ``AlreadyExists`` error if there is already a unit with the supplied
        application name.
        """
        api = Deployer(create_volume_service(self),
                       gear_client=FakeGearClient())
        application = Application(
            name=b'site-example.com',
            image=DockerImage(repository=u'clusterhq/flocker',
                              tag=u'release-14.0')
        )

        result1 = api.start_application(application=application)
        self.successResultOf(result1)

        result2 = api.start_application(application=application)
        self.failureResultOf(result2, AlreadyExists)


class DeployerStopApplicationTests(SynchronousTestCase):
    """
    Tests for ``Deployer.stop_application``.
    """
    def test_stop(self):
        """
        ``Deployer.stop_application`` accepts an application object and returns
        a `Deferred` which fires when the `gear` unit has been removed.
        """
        fake_gear = FakeGearClient()
        api = Deployer(create_volume_service(self), gear_client=fake_gear)
        application = Application(
            name=b'site-example.com',
            image=DockerImage(repository=u'clusterhq/flocker',
                              tag=u'release-14.0')
        )

        api.start_application(application=application)
        existed = fake_gear.exists(application.name)
        stop_result = api.stop_application(application=application)
        exists_result = fake_gear.exists(unit_name=application.name)

        self.assertEqual(
            (None, True, False),
            (self.successResultOf(stop_result),
             self.successResultOf(existed),
             self.successResultOf(exists_result))
        )

    def test_does_not_exist(self):
        """
        ``Deployer.stop_application`` does not errback if the application does
        not exist.
        """
        api = Deployer(create_volume_service(self),
                       gear_client=FakeGearClient())
        application = Application(
            name=b'site-example.com',
            image=DockerImage(repository=u'clusterhq/flocker',
                              tag=u'release-14.0')
        )
        result = api.stop_application(application=application)
        result = self.successResultOf(result)

        self.assertIs(None, result)


class DeployerDiscoverNodeConfigurationTests(SynchronousTestCase):
    """
    Tests for ``Deployer.discover_node_configuration``.
    """
    def test_discover_none(self):
        """
        ``Deployer.discover_node_configuration`` returns an empty list if
        there are no active `geard` units on the host.
        """
        fake_gear = FakeGearClient(units={})
        api = Deployer(create_volume_service(self), gear_client=fake_gear)
        d = api.discover_node_configuration()

        self.assertEqual([], self.successResultOf(d))

    def test_discover_one(self):
        """
        ``Deployer.discover_node_configuration`` returns a list of
        ``Application``\ s; one for each active `gear` unit.
        """
        expected_application_name = u'site-example.com'
        unit = Unit(name=expected_application_name, activation_state=u'active')
        fake_gear = FakeGearClient(units={expected_application_name: unit})
        application = Application(name=unit.name)
        api = Deployer(create_volume_service(self), gear_client=fake_gear)
        d = api.discover_node_configuration()

        self.assertEqual([application], self.successResultOf(d))

    def test_discover_multiple(self):
        """
        ``Deployer.discover_node_configuration`` returns an ``Application``
        for every `active` `gear` ``Unit`` on the host.
        """
        unit1 = Unit(name=u'site-example.com', activation_state=u'active')
        unit2 = Unit(name=u'site-example.net', activation_state=u'active')
        units = {unit1.name: unit1, unit2.name: unit2}

        fake_gear = FakeGearClient(units=units)
        applications = [Application(name=unit.name) for unit in units.values()]
        api = Deployer(create_volume_service(self), gear_client=fake_gear)
        d = api.discover_node_configuration()

        self.assertEqual(sorted(applications), sorted(self.successResultOf(d)))

    def test_discover_locally_owned_volume(self):
        """
        Locally owned volumes are added to ``Application`` with same name as
        an ``AttachedVolume``.
        """
        unit1 = Unit(name=u'site-example.com', activation_state=u'active')
        unit2 = Unit(name=u'site-example.net', activation_state=u'active')
        units = {unit1.name: unit1, unit2.name: unit2}

        volume_service = create_volume_service(self)
        self.successResultOf(volume_service.create(u"site-example.com"))
        self.successResultOf(volume_service.create(u"site-example.net"))

        # Eventually when https://github.com/ClusterHQ/flocker/issues/289
        # is fixed the mountpoint should actually be specified.
        fake_gear = FakeGearClient(units=units)
        applications = [Application(name=unit.name,
                                    volume=AttachedVolume(name=unit.name,
                                                          mountpoint=None))
                        for unit in units.values()]
        api = Deployer(volume_service, gear_client=fake_gear)
        d = api.discover_node_configuration()

        self.assertEqual(sorted(applications), sorted(self.successResultOf(d)))

    def test_discover_remotely_owned_volumes_ignored(self):
        """
        Remotely owned volumes are not added to the discovered ``Application``
        instances even if they have the same name.
        """
        unit = Unit(name=u'site-example.com', activation_state=u'active')
        units = {unit.name: unit}

        volume_service = create_volume_service(self)
        volume = Volume(uuid=unicode(uuid4()), name=u"site-example.com",
                        _pool=volume_service._pool)
        self.successResultOf(volume._pool.create(volume))

        fake_gear = FakeGearClient(units=units)
        applications = [Application(name=unit.name)]
        api = Deployer(volume_service, gear_client=fake_gear)
        d = api.discover_node_configuration()
        self.assertEqual(sorted(applications), sorted(self.successResultOf(d)))


class DeployerCalculateNecessaryStateChangesTests(SynchronousTestCase):
    """
    Tests for ``Deployer.calculate_necessary_state_changes``.
    """
    def test_no_state_changes(self):
        """
        ``Deployer.calculate_necessary_state_changes`` returns a ``Deferred``
        which fires with a :class:`StateChanges` instance indicating that no
        changes are necessary when there are no applications running or
        desired, and no proxies exist or are desired.
        """
        fake_gear = FakeGearClient(units={})
        api = Deployer(create_volume_service(self), gear_client=fake_gear)
        desired = Deployment(nodes=frozenset())
        d = api.calculate_necessary_state_changes(desired_state=desired,
                                                  hostname=u'node.example.com')
        expected = StateChanges(applications_to_start=set(),
                                applications_to_stop=set(),
                                proxies=set())
        self.assertEqual(expected, self.successResultOf(d))

    def test_application_needs_stopping(self):
        """
        ``Deployer.calculate_necessary_state_changes`` specifies that an
        application must be stopped when it is running but not desired.
        """
        unit = Unit(name=u'site-example.com', activation_state=u'active')

        fake_gear = FakeGearClient(units={unit.name: unit})
        api = Deployer(create_volume_service(self), gear_client=fake_gear)
        desired = Deployment(nodes=frozenset())
        d = api.calculate_necessary_state_changes(desired_state=desired,
                                                  hostname=u'node.example.com')
        to_stop = set([Application(name=unit.name)])
        expected = StateChanges(applications_to_start=set(),
                                applications_to_stop=to_stop)
        self.assertEqual(expected, self.successResultOf(d))

    def test_application_needs_starting(self):
        """
        ``Deployer.calculate_necessary_state_changes`` specifies that an
        application must be started when it is desired on the given node but
        not running.
        """
        fake_gear = FakeGearClient(units={})
        api = Deployer(create_volume_service(self), gear_client=fake_gear)
        application = Application(
            name=b'mysql-hybridcluster',
            image=DockerImage(repository=u'clusterhq/flocker',
                              tag=u'release-14.0')
        )

        nodes = frozenset([
            Node(
                hostname=u'node.example.com',
                applications=frozenset([application])
            )
        ])

        desired = Deployment(nodes=nodes)
        d = api.calculate_necessary_state_changes(desired_state=desired,
                                                  hostname=u'node.example.com')
        expected = StateChanges(applications_to_start=set([application]),
                                applications_to_stop=set())
        self.assertEqual(expected, self.successResultOf(d))

    def test_only_this_node(self):
        """
        ``Deployer.calculate_necessary_state_changes`` does not specify that an
        application must be started if the desired changes apply to a different
        node.
        """
        fake_gear = FakeGearClient(units={})
        api = Deployer(create_volume_service(self), gear_client=fake_gear)
        application = Application(
            name=b'mysql-hybridcluster',
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
        d = api.calculate_necessary_state_changes(desired_state=desired,
                                                  hostname=u'node.example.com')
        expected = StateChanges(applications_to_start=set(),
                                applications_to_stop=set())
        self.assertEqual(expected, self.successResultOf(d))

    def test_no_change_needed(self):
        """
        ``Deployer.calculate_necessary_state_changes`` does not specify that an
        application must be started or stopped if the desired configuration
        is the same as the current configuration.
        """
        unit = Unit(name=u'mysql-hybridcluster', activation_state=u'active')

        fake_gear = FakeGearClient(units={unit.name: unit})
        api = Deployer(create_volume_service(self), gear_client=fake_gear)

        application = Application(
            name=u'mysql-hybridcluster',
            image=DockerImage(repository=u'clusterhq/flocker',
                              tag=u'release-14.0'),
            ports=frozenset([]),
        )

        nodes = frozenset([
            Node(
                hostname=u'node.example.com',
                applications=frozenset([application])
            )
        ])

        desired = Deployment(nodes=nodes)
        d = api.calculate_necessary_state_changes(desired_state=desired,
                                                  hostname=u'node.example.com')
        expected = StateChanges(applications_to_start=set(),
                                applications_to_stop=set())
        self.assertEqual(expected, self.successResultOf(d))

    def test_node_not_described(self):
        """
        ``Deployer.calculate_necessary_state_changes`` specifies that all
        applications on a node must be stopped if the desired configuration
        does not include that node.
        """
        unit = Unit(name=u'mysql-hybridcluster', activation_state=u'active')

        fake_gear = FakeGearClient(units={unit.name: unit})
        api = Deployer(create_volume_service(self), gear_client=fake_gear)
        desired = Deployment(nodes=frozenset([]))
        d = api.calculate_necessary_state_changes(desired_state=desired,
                                                  hostname=u'node.example.com')
        to_stop = set([Application(name=unit.name)])
        expected = StateChanges(applications_to_start=set(),
                                applications_to_stop=to_stop)
        self.assertEqual(expected, self.successResultOf(d))


class DeployerChangeNodeStateTests(SynchronousTestCase):
    """
    Tests for ``Deployer.change_node_state``.
    """

    def test_applications_stopped(self):
        """
        Existing applications which are not in the desired configuration are
        stopped.
        """
        unit = Unit(name=u'mysql-hybridcluster', activation_state=u'active')
        fake_gear = FakeGearClient(units={unit.name: unit})
        api = Deployer(create_volume_service(self), gear_client=fake_gear)
        desired = Deployment(nodes=frozenset())

        d = api.change_node_state(desired_state=desired,
                                  hostname=u'node.example.com')
        d.addCallback(lambda _: api.discover_node_configuration())

        self.assertEqual([], self.successResultOf(d))

    def test_applications_started(self):
        """
        Applications which are in the desired configuration are started.
        """
        fake_gear = FakeGearClient(units={})
        api = Deployer(create_volume_service(self), gear_client=fake_gear)
        expected_application_name = u'mysql-hybridcluster'
        application = Application(
            name=expected_application_name,
            image=DockerImage(repository=u'clusterhq/flocker',
                              tag=u'release-14.0')
        )

        nodes = frozenset([
            Node(
                hostname=u'node.example.com',
                applications=frozenset([application])
            )
        ])

        desired = Deployment(nodes=nodes)
        d = api.change_node_state(desired_state=desired,
                                  hostname=u'node.example.com')
        d.addCallback(lambda _: api.discover_node_configuration())

        expected_application = Application(name=expected_application_name)
        self.assertEqual([expected_application], self.successResultOf(d))

    def test_first_failure_pass_through(self):
        """
        The first failure in the operations performed by
        ``Deployer.change_node_state`` is passed through.
        """
        unit = Unit(name=u'site-hybridcluster.com', activation_state=u'active')
        fake_gear = FakeGearClient(units={unit.name: unit})
        api = Deployer(create_volume_service(self), gear_client=fake_gear)

        application = Application(
            name=b'mysql-hybridcluster',
            image=DockerImage(repository=u'clusterhq/flocker',
                              tag=u'release-14.0')
        )

        nodes = frozenset([
            Node(
                hostname=u'node.example.com',
                applications=frozenset([application])
            )
        ])

        desired = Deployment(nodes=nodes)

        class SentinelException(Exception):
            """
            An exception raised for test purposes from
            ``Deployer.stop_application``.
            """

        expected_exception = SentinelException()

        self.patch(
            api, 'stop_application',
            lambda application: fail(expected_exception))

        d = api.change_node_state(desired_state=desired,
                                  hostname=u'node.example.com')

        failure = self.failureResultOf(d, FirstError)
        self.assertEqual(expected_exception, failure.value.subFailure.value)

    def test_continue_on_failure(self):
        """
        Failures in the operations performed by ``Deployer.change_node_state``
        do not prevent further changes being made.

        Two applications are configured to be started, but attempts to start
        application1 will result in failure. We then assert that the
        ``FakeGearClient`` has still been asked to start application2
        """
        local_hostname = u'node.example.com'
        fake_gear = FakeGearClient()
        api = Deployer(create_volume_service(self), gear_client=fake_gear)

        application1 = Application(
            name=b'mysql-hybridcluster',
            image=DockerImage(repository=u'clusterhq/mysql',
                              tag=u'latest')
        )

        application2 = Application(
            name=b'site-hybridcluster',
            image=DockerImage(repository=u'clusterhq/wordpress',
                              tag=u'latest')
        )

        nodes = frozenset([
            Node(
                hostname=local_hostname,
                applications=frozenset([application1, application2])
            )
        ])

        desired = Deployment(nodes=nodes)

        real_start_application = api.start_application

        def fake_start(application):
            """
            Return a failure for attempts to start application1
            """
            if application.name == application1.name:
                return fail(Exception('First start failure.'))
            else:
                return real_start_application(application)

        self.patch(api, 'start_application', fake_start)

        d = api.change_node_state(desired_state=desired,
                                  hostname=local_hostname)

        self.failureResultOf(d, FirstError)
        self.assertIn(application2.name, fake_gear._units)
