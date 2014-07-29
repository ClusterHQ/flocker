# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for ``flocker.node._deploy``.
"""

from uuid import uuid4

from twisted.internet.defer import fail, FirstError, succeed
from twisted.trial.unittest import SynchronousTestCase

from .. import (Deployer, Application, DockerImage, Deployment, Node,
                StateChanges, Port, NodeState)
from .._model import VolumeHandoff, AttachedVolume
from ..gear import GearClient, FakeGearClient, AlreadyExists, Unit, PortMap
from ...route import Proxy, make_memory_network
from ...route._iptables import HostNetwork
from ...testtools import create_volume_service
from ...volume.service import Volume


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
        ``Deployer._network`` is a ``HostNetwork`` by default.
        """
        self.assertIsInstance(Deployer(None)._network, HostNetwork)

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


# This models an application that has a volume.
APPLICATION_WITH_VOLUME_NAME = b"psql-clusterhq"
APPLICATION_WITH_VOLUME_MOUNTPOINT = b"/var/lib/postgresql"
APPLICATION_WITH_VOLUME = Application(
    name=APPLICATION_WITH_VOLUME_NAME,
    image=DockerImage(repository=u'clusterhq/postgresql',
                      tag=u'9.1'),
    volume=AttachedVolume(
        # XXX For now we require volume names match application names,
        # see https://github.com/ClusterHQ/flocker/issues/49
        name=APPLICATION_WITH_VOLUME_NAME,
        mountpoint=APPLICATION_WITH_VOLUME_MOUNTPOINT,
    )
)


class DeployerDiscoverNodeConfigurationTests(SynchronousTestCase):
    """
    Tests for ``Deployer.discover_node_configuration``.
    """
    def test_discover_none(self):
        """
        ``Deployer.discover_node_configuration`` returns an empty
        ``NodeState`` if there are no `geard` units on the host.
        """
        fake_gear = FakeGearClient(units={})
        api = Deployer(create_volume_service(self), gear_client=fake_gear)
        d = api.discover_node_configuration()

        self.assertEqual(NodeState(running=[], not_running=[]),
                         self.successResultOf(d))

    def test_discover_one(self):
        """
        ``Deployer.discover_node_configuration`` returns ``NodeState`` with a
        a list of running ``Application``\ s; one for each active `gear`
        unit.
        """
        expected_application_name = u'site-example.com'
        unit = Unit(name=expected_application_name, activation_state=u'active')
        fake_gear = FakeGearClient(units={expected_application_name: unit})
        application = Application(name=unit.name)
        api = Deployer(create_volume_service(self), gear_client=fake_gear)
        d = api.discover_node_configuration()

        self.assertEqual(NodeState(running=[application], not_running=[]),
                         self.successResultOf(d))

    def test_discover_multiple(self):
        """
        ``Deployer.discover_node_configuration`` returns a ``NodeState`` with
        a running ``Application`` for every active or activating gear
        ``Unit`` on the host.
        """
        unit1 = Unit(name=u'site-example.com', activation_state=u'active')
        unit2 = Unit(name=u'site-example.net', activation_state=u'activating')
        units = {unit1.name: unit1, unit2.name: unit2}

        fake_gear = FakeGearClient(units=units)
        applications = [Application(name=unit.name) for unit in units.values()]
        api = Deployer(create_volume_service(self), gear_client=fake_gear)
        d = api.discover_node_configuration()

        self.assertEqual(sorted(applications),
                         sorted(self.successResultOf(d).running))

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

        self.assertEqual(sorted(applications),
                         sorted(self.successResultOf(d).running))

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
        self.assertEqual(sorted(applications),
                         sorted(self.successResultOf(d).running))

    def test_discover_activating_units(self):
        """
        Units that are currently not active but are starting up are considered
        to be running by ``discover_node_configuration()``.
        """
        unit = Unit(name=u'site-example.com', activation_state=u'activating')
        units = {unit.name: unit}

        fake_gear = FakeGearClient(units=units)
        applications = [Application(name=unit.name)]
        api = Deployer(create_volume_service(self), gear_client=fake_gear)
        d = api.discover_node_configuration()

        self.assertEqual(NodeState(running=applications, not_running=[]),
                         self.successResultOf(d))

    def test_not_running_units(self):
        """
        Units that are neither active nor activating are considered to be not
        running by ``discover_node_configuration()``.
        """
        unit1 = Unit(name=u'site-example.com',
                     activation_state=u'deactivating')
        unit2 = Unit(name=u'site-example.net', activation_state=u'failed')
        unit3 = Unit(name=u'site-example3.net', activation_state=u'inactive')
        unit4 = Unit(name=u'site-example4.net', activation_state=u'madeup')
        units = {unit1.name: unit1, unit2.name: unit2, unit3.name: unit3,
                 unit4.name: unit4}

        fake_gear = FakeGearClient(units=units)
        applications = [Application(name=unit.name) for unit in units.values()]
        applications.sort()
        api = Deployer(create_volume_service(self), gear_client=fake_gear)
        d = api.discover_node_configuration()
        result = self.successResultOf(d)
        result.not_running.sort()

        self.assertEqual(NodeState(running=[], not_running=applications),
                         result)

# A deployment with no information:
EMPTY = Deployment(nodes=frozenset())


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
        api = Deployer(create_volume_service(self), gear_client=fake_gear,
                       network=make_memory_network())
        desired = Deployment(nodes=frozenset())
        d = api.calculate_necessary_state_changes(desired_state=desired,
                                                  current_cluster_state=EMPTY,
                                                  hostname=u'node.example.com')
        expected = StateChanges(applications_to_start=set(),
                                applications_to_stop=set(),
                                proxies=set())
        self.assertEqual(expected, self.successResultOf(d))

    def test_proxy_needs_creating(self):
        """
        ``Deployer.calculate_necessary_state_changes`` returns a
        ``StateChanges`` instance containing a list of ``Proxy`` objects. One
        for each port exposed by ``Application``\ s hosted on a remote nodes.
        """
        fake_gear = FakeGearClient(units={})
        api = Deployer(create_volume_service(self), gear_client=fake_gear,
                       network=make_memory_network())
        expected_destination_port = 1001
        expected_destination_host = u'node1.example.com'
        port = Port(internal_port=3306,
                    external_port=expected_destination_port)
        application = Application(
            name=b'mysql-hybridcluster',
            image=DockerImage(repository=u'clusterhq/mysql',
                              tag=u'release-14.0'),
            ports=frozenset([port]),
        )

        nodes = frozenset([
            Node(
                hostname=expected_destination_host,
                applications=frozenset([application])
            )
        ])

        desired = Deployment(nodes=nodes)
        d = api.calculate_necessary_state_changes(
            desired_state=desired, current_cluster_state=EMPTY,
            hostname=u'node2.example.com')
        proxy = Proxy(ip=expected_destination_host,
                      port=expected_destination_port)
        expected = StateChanges(applications_to_start=frozenset(),
                                applications_to_stop=frozenset(),
                                proxies=frozenset([proxy]))
        self.assertEqual(expected, self.successResultOf(d))

    def test_proxy_empty(self):
        """
        ``Deployer.calculate_necessary_state_changes`` returns a
        ``StateChanges`` instance containing an empty `proxies`
        list if there are no remote applications that need proxies.
        """
        network = make_memory_network()
        api = Deployer(create_volume_service(self),
                       gear_client=FakeGearClient(),
                       network=network)
        desired = Deployment(nodes=frozenset())
        d = api.calculate_necessary_state_changes(
            desired_state=desired, current_cluster_state=EMPTY,
            hostname=u'node2.example.com')
        expected = StateChanges(applications_to_start=set(),
                                applications_to_stop=set(),
                                proxies=frozenset())
        self.assertEqual(expected, self.successResultOf(d))

    def test_application_needs_stopping(self):
        """
        ``Deployer.calculate_necessary_state_changes`` specifies that an
        application must be stopped when it is running but not desired.
        """
        unit = Unit(name=u'site-example.com', activation_state=u'active')

        fake_gear = FakeGearClient(units={unit.name: unit})
        api = Deployer(create_volume_service(self), gear_client=fake_gear,
                       network=make_memory_network())
        desired = Deployment(nodes=frozenset())
        d = api.calculate_necessary_state_changes(desired_state=desired,
                                                  current_cluster_state=EMPTY,
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
        api = Deployer(create_volume_service(self), gear_client=fake_gear,
                       network=make_memory_network())
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
                                                  current_cluster_state=EMPTY,
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
        api = Deployer(create_volume_service(self), gear_client=fake_gear,
                       network=make_memory_network())
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
                                                  current_cluster_state=EMPTY,
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
        api = Deployer(create_volume_service(self), gear_client=fake_gear,
                       network=make_memory_network())

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
                                                  current_cluster_state=EMPTY,
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
        api = Deployer(create_volume_service(self), gear_client=fake_gear,
                       network=make_memory_network())
        desired = Deployment(nodes=frozenset([]))
        d = api.calculate_necessary_state_changes(desired_state=desired,
                                                  current_cluster_state=EMPTY,
                                                  hostname=u'node.example.com')
        to_stop = set([Application(name=unit.name)])
        expected = StateChanges(applications_to_start=set(),
                                applications_to_stop=to_stop)
        self.assertEqual(expected, self.successResultOf(d))

    def test_volume_created(self):
        """
        ``Deployer.calculate_necessary_state_changes`` specifies that a new
        volume must be created if the desired configuration specifies that an
        application which was previously running nowhere is going to be running
        on *this* node and that application requires a volume.
        """
        hostname = u"node1.example.com"

        # The application is not running here - therefore there is no gear unit
        # for it.
        gear = FakeGearClient(units={})

        # The discovered current configuration of the cluster also reflects
        # this.
        current = Deployment(nodes=frozenset({
            Node(hostname=hostname, applications=frozenset()),
        }))

        api = Deployer(
            create_volume_service(self), gear_client=gear,
            network=make_memory_network()
        )

        node = Node(
            hostname=hostname,
            applications=frozenset({APPLICATION_WITH_VOLUME}),
        )

        # This completely expresses the configuration for a cluster of one node
        # with one application which requires a volume.  It's the state we
        # should get to with the changes calculated below.
        desired = Deployment(nodes=frozenset({node}))

        calculating = api.calculate_necessary_state_changes(
            desired_state=desired,
            current_cluster_state=current,
            hostname=hostname,
        )

        changes = self.successResultOf(calculating)

        expected = StateChanges(
            # The application isn't running here so it needs to be started.
            applications_to_start={
                APPLICATION_WITH_VOLUME,
            },
            applications_to_stop=set(),
            volumes_to_handoff=set(),
            volumes_to_wait_for=set(),
            volumes_to_create={
                AttachedVolume(
                    name=APPLICATION_WITH_VOLUME_NAME,
                    mountpoint=APPLICATION_WITH_VOLUME_MOUNTPOINT
                ),
            },
        )

        self.assertEqual(expected, changes)

    def test_volume_wait(self):
        """
        ``Deployer.calculate_necessary_state_changes`` specifies that the
        volume for an application which was previously running on another node
        must be waited for, in anticipation of that node handing it off to us.
        """
        # The application is not running here - therefore there is no gear unit
        # for it.
        gear = FakeGearClient(units={})

        node = Node(
            hostname=u"node1.example.com",
            applications=frozenset(),
        )
        another_node = Node(
            hostname=u"node2.example.com",
            applications=frozenset({APPLICATION_WITH_VOLUME}),
        )

        # The discovered current configuration of the cluster reveals the
        # application is running somewhere else.
        current = Deployment(nodes=frozenset([node, another_node]))

        api = Deployer(
            create_volume_service(self), gear_client=gear,
            network=make_memory_network()
        )

        desired = Deployment(nodes=frozenset({
            Node(hostname=node.hostname,
                 applications=another_node.applications),
            Node(hostname=another_node.hostname,
                 applications=frozenset()),
        }))

        calculating = api.calculate_necessary_state_changes(
            desired_state=desired,
            current_cluster_state=current,
            hostname=node.hostname,
        )

        changes = self.successResultOf(calculating)

        expected = StateChanges(
            # The application isn't running here so it needs to be started.
            applications_to_start={
                APPLICATION_WITH_VOLUME,
            },
            applications_to_stop=set(),
            volumes_to_handoff=set(),
            volumes_to_wait_for={
                AttachedVolume(
                    name=APPLICATION_WITH_VOLUME_NAME,
                    mountpoint=APPLICATION_WITH_VOLUME_MOUNTPOINT,
                ),
            },
            volumes_to_create=set(),
        )

        self.assertEqual(expected, changes)

    def test_volume_handoff(self):
        """
        ``Deployer.calculate_necessary_state_changes`` specifies that the
        volume for an application which was previously running on this node but
        is now running on another node must be handed off.
        """
        # The application is running here.
        unit = Unit(
            name=APPLICATION_WITH_VOLUME_NAME, activation_state=u'active'
        )
        gear = FakeGearClient(units={unit.name: unit})

        node = Node(
            hostname=u"node1.example.com",
            applications=frozenset({APPLICATION_WITH_VOLUME}),
        )
        another_node = Node(
            hostname=u"node2.example.com",
            applications=frozenset(),
        )

        # The discovered current configuration of the cluster reveals the
        # application is running here.
        current = Deployment(nodes=frozenset([node, another_node]))

        api = Deployer(
            create_volume_service(self), gear_client=gear,
            network=make_memory_network()
        )

        desired = Deployment(nodes=frozenset({
            Node(hostname=node.hostname,
                 applications=frozenset()),
            Node(hostname=another_node.hostname,
                 applications=node.applications),
        }))

        calculating = api.calculate_necessary_state_changes(
            desired_state=desired,
            current_cluster_state=current,
            hostname=node.hostname,
        )

        changes = self.successResultOf(calculating)

        volume = AttachedVolume(
            name=APPLICATION_WITH_VOLUME_NAME,
            mountpoint=APPLICATION_WITH_VOLUME_MOUNTPOINT,
        )

        expected = StateChanges(
            # The application is running here so it needs to be stopped.
            applications_to_start=set(),
            applications_to_stop={
                Application(name=APPLICATION_WITH_VOLUME_NAME),
            },
            # And the volume for the application needs to be handed off.
            volumes_to_handoff={
                VolumeHandoff(volume=volume, hostname=another_node.hostname),
            },
            volumes_to_wait_for=set(),
            volumes_to_create=set(),
        )

        self.assertEqual(expected, changes)

    def test_no_volume_changes(self):
        """
        ``Deployer.calculate_necessary_state_changes`` specifies no work for
        the volume if an application which was previously running on this
        node continues to run on this node.
        """
        # The application is running here.
        unit = Unit(
            name=APPLICATION_WITH_VOLUME_NAME, activation_state=u'active'
        )
        gear = FakeGearClient(units={unit.name: unit})

        node = Node(
            hostname=u"node1.example.com",
            applications=frozenset({APPLICATION_WITH_VOLUME}),
        )
        another_node = Node(
            hostname=u"node2.example.com",
            applications=frozenset(),
        )

        # The discovered current configuration of the cluster reveals the
        # application is running here.
        current = Deployment(nodes=frozenset([node, another_node]))

        api = Deployer(
            create_volume_service(self), gear_client=gear,
            network=make_memory_network()
        )

        calculating = api.calculate_necessary_state_changes(
            desired_state=current,
            current_cluster_state=current,
            hostname=node.hostname,
        )

        changes = self.successResultOf(calculating)

        expected = StateChanges(
            applications_to_start=set(),
            applications_to_stop=set(),
            volumes_to_handoff=set(),
            volumes_to_wait_for=set(),
            volumes_to_create=set(),
        )

        self.assertEqual(expected, changes)

    def test_local_not_running_applications_restarted(self):
        """
        Applications that are not running but are supposed to be on the local
        node are added to the list of applications to restart.
        """
        unit = Unit(name=u'mysql-hybridcluster', activation_state=u'inactive')

        fake_gear = FakeGearClient(units={unit.name: unit})
        api = Deployer(create_volume_service(self), gear_client=fake_gear,
                       network=make_memory_network())
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
                                                  current_cluster_state=EMPTY,
                                                  hostname=u'node.example.com')
        to_restart = set([application])
        expected = StateChanges(applications_to_start=set(),
                                applications_to_stop=set(),
                                applications_to_restart=to_restart)
        self.assertEqual(expected, self.successResultOf(d))

    def test_not_local_not_running_applications_stopped(self):
        """
        Applications that are not running and are supposed to be on the local
        node are added to the list of applications to stop.
        """
        unit = Unit(name=u'mysql-hybridcluster', activation_state=u'inactive')

        fake_gear = FakeGearClient(units={unit.name: unit})
        api = Deployer(create_volume_service(self), gear_client=fake_gear,
                       network=make_memory_network())

        desired = Deployment(nodes=frozenset())
        d = api.calculate_necessary_state_changes(desired_state=desired,
                                                  current_cluster_state=EMPTY,
                                                  hostname=u'node.example.com')
        to_stop = set([Application(name=unit.name)])
        expected = StateChanges(applications_to_start=set(),
                                applications_to_stop=to_stop,
                                applications_to_restart=set())
        self.assertEqual(expected, self.successResultOf(d))


class DeployerApplyChangesTests(SynchronousTestCase):
    """
    Tests for ``Deployer._apply_changes``.
    """
    def test_proxies_added(self):
        """
        Proxies which are required are added.
        """
        fake_network = make_memory_network()
        api = Deployer(
            create_volume_service(self), gear_client=FakeGearClient(),
            network=fake_network)

        expected_proxy = Proxy(ip=u'192.0.2.100', port=3306)
        desired_changes = StateChanges(
            applications_to_start=frozenset(),
            applications_to_stop=frozenset(),
            proxies=frozenset([expected_proxy])
        )
        d = api._apply_changes(desired_changes)
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
        api = Deployer(
            create_volume_service(self), gear_client=FakeGearClient(),
            network=fake_network)

        desired_changes = StateChanges(
            applications_to_start=frozenset(),
            applications_to_stop=frozenset(),
        )
        d = api._apply_changes(desired_changes)
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

        api = Deployer(
            create_volume_service(self), gear_client=FakeGearClient(),
            network=fake_network)

        desired_changes = StateChanges(
            applications_to_start=frozenset(),
            applications_to_stop=frozenset(),
            proxies=frozenset([required_proxy1, required_proxy2])
        )

        d = api._apply_changes(desired_changes)

        self.successResultOf(d)
        self.assertEqual(
            set([required_proxy1, required_proxy2]),
            set(fake_network.enumerate_proxies())
        )

    def test_delete_proxy_errors_as_errbacks(self):
        """
        Exceptions raised in `delete_proxy` operations are reported as
        failures in the returned deferred.
        """
        fake_network = make_memory_network()
        fake_network.create_proxy_to(ip=u'192.0.2.100', port=3306)
        fake_network.delete_proxy = lambda proxy: 1/0

        api = Deployer(
            create_volume_service(self), gear_client=FakeGearClient(),
            network=fake_network)

        desired_changes = StateChanges(
            applications_to_start=frozenset(),
            applications_to_stop=frozenset(),
        )
        d = api._apply_changes(desired_changes)
        exception = self.failureResultOf(d, FirstError)
        self.assertIsInstance(
            exception.value.subFailure.value,
            ZeroDivisionError
        )

    def test_create_proxy_errors_as_errbacks(self):
        """
        Exceptions raised in `create_proxy_to` operations are reported as
        failures in the returned deferred.
        """
        fake_network = make_memory_network()
        fake_network.create_proxy_to = lambda ip, port: 1/0

        api = Deployer(
            create_volume_service(self), gear_client=FakeGearClient(),
            network=fake_network)

        desired_changes = StateChanges(
            applications_to_start=frozenset(),
            applications_to_stop=frozenset(),
            proxies=frozenset([Proxy(ip=u'192.0.2.100', port=3306)])
        )
        d = api._apply_changes(desired_changes)
        exception = self.failureResultOf(d, FirstError)
        self.assertIsInstance(
            exception.value.subFailure.value,
            ZeroDivisionError
        )

    def test_restarts(self):
        """
        Applications listed in ``StateChanges.applications_to_restart`` are
        reactivated.
        """
        unit = Unit(name=u'mysql-hybridcluster', activation_state=u'failed')
        fake_gear = FakeGearClient(units={unit.name: unit})
        api = Deployer(
            create_volume_service(self), gear_client=fake_gear,
            network=make_memory_network())

        application = Application(
            name=u'mysql-hybridcluster',
            image=DockerImage.from_string(u'clusterhq/flocker'),
        )

        desired_changes = StateChanges(
            applications_to_start=frozenset(),
            applications_to_stop=frozenset(),
            applications_to_restart=frozenset([application]))
        api._apply_changes(desired_changes)

        # The activation state tells us the unit was started. We know a
        # stop preceded the starting of the unit, because otherwise
        # starting would complain with an AlreadyExists.
        self.assertEqual(self.successResultOf(fake_gear.list()),
                         set([Unit(name=u'mysql-hybridcluster',
                                   activation_state=u'active')]))


class DeployerChangeNodeStateTests(SynchronousTestCase):
    """
    Tests for ``Deployer.change_node_state``.

    XXX: Many of these tests are exercising code which has now been refactored
    into `Deployer._apply_changes`. As such, they can be moved to the
    `DeployerApplyChangesTests` testcase and simplified. See
    https://github.com/ClusterHQ/flocker/issues/321
    """
    def test_applications_stopped(self):
        """
        Existing applications which are not in the desired configuration are
        stopped.
        """
        unit = Unit(name=u'mysql-hybridcluster', activation_state=u'active')
        fake_gear = FakeGearClient(units={unit.name: unit})
        api = Deployer(create_volume_service(self), gear_client=fake_gear,
                       network=make_memory_network())
        desired = Deployment(nodes=frozenset())

        d = api.change_node_state(desired_state=desired,
                                  current_cluster_state=EMPTY,
                                  hostname=u'node.example.com')
        d.addCallback(lambda _: api.discover_node_configuration())

        self.assertEqual(NodeState(running=[], not_running=[]),
                         self.successResultOf(d))

    def test_applications_started(self):
        """
        Applications which are in the desired configuration are started.
        """
        fake_gear = FakeGearClient(units={})
        api = Deployer(create_volume_service(self), gear_client=fake_gear,
                       network=make_memory_network())
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
                                  current_cluster_state=EMPTY,
                                  hostname=u'node.example.com')
        d.addCallback(lambda _: api.discover_node_configuration())

        expected_application = Application(name=expected_application_name)
        self.assertEqual(
            NodeState(running=[expected_application], not_running=[]),
            self.successResultOf(d))

    def test_first_failure_pass_through(self):
        """
        The first failure in the operations performed by
        ``Deployer.change_node_state`` is passed through.
        """
        unit = Unit(name=u'site-hybridcluster.com', activation_state=u'active')
        fake_gear = FakeGearClient(units={unit.name: unit})
        api = Deployer(create_volume_service(self), gear_client=fake_gear,
                       network=make_memory_network())

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
                                  current_cluster_state=EMPTY,
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
        api = Deployer(create_volume_service(self), gear_client=fake_gear,
                       network=make_memory_network())

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
                                  current_cluster_state=EMPTY,
                                  hostname=local_hostname)

        self.failureResultOf(d, FirstError)
        self.assertIn(application2.name, fake_gear._units)

    def test_arguments(self):
        """
        The passed in arguments passed on in turn to
        ``calculate_necessary_state_changes``.
        """
        desired = object()
        state = object()
        host = object()
        api = Deployer(create_volume_service(self),
                       gear_client=FakeGearClient(),
                       network=make_memory_network())
        arguments = []

        def calculate(desired_state, current_cluster_state, hostname):
            arguments.extend([desired_state, current_cluster_state, hostname])
            return succeed(StateChanges(applications_to_start=[],
                                        applications_to_stop=[]))
        api.calculate_necessary_state_changes = calculate
        api.change_node_state(desired, state, host)
        self.assertEqual(arguments, [desired, state, host])
