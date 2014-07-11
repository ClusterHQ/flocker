# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for ``flocker.node._deploy``.
"""

from twisted.trial.unittest import SynchronousTestCase

from .. import (Deployer, Application, DockerImage, Deployment, Node,
                StateChanges)
from ..gear import GearClient, FakeGearClient, AlreadyExists, Unit


class DeployerAttributesTests(SynchronousTestCase):
    """
    Tests for attributes and initialiser arguments of `Deployer`.
    """
    def test_gear_client_default(self):
        """
        ``Deployer._gear_client`` is a ``GearClient`` by default.
        """
        self.assertIsInstance(
            Deployer()._gear_client,
            GearClient
        )

    def test_gear_override(self):
        """
        ``Deployer._gear_client`` can be overridden in the constructor.
        """
        dummy_gear_client = object()
        self.assertIs(
            dummy_gear_client,
            Deployer(gear_client=dummy_gear_client)._gear_client
        )


class DeployerStartContainerTests(SynchronousTestCase):
    """
    Tests for `Deployer.start_container`.
    """
    def test_start(self):
        """
        `Deployer.start_container` accepts an application object and returns
        a deferred which fires when the `gear` unit has been added and started.
        """
        fake_gear = FakeGearClient()
        api = Deployer(gear_client=fake_gear)
        docker_image = DockerImage(repository=u'clusterhq/flocker',
                                   tag=u'release-14.0')
        application = Application(
            name=b'site-example.com',
            image=docker_image
        )
        start_result = api.start_container(application=application)
        exists_result = fake_gear.exists(unit_name=application.name)

        self.assertEqual(
            (None, True, docker_image.full_name),
            (self.successResultOf(start_result),
             self.successResultOf(exists_result),
             fake_gear._units[application.name].container_image)
        )

    def test_already_exists(self):
        """
        ``Deployer.start_container`` returns a deferred which errbacks with
        an ``AlreadyExists`` error if there is already a unit with the supplied
        application name.
        """
        api = Deployer(gear_client=FakeGearClient())
        application = Application(
            name=b'site-example.com',
            image=DockerImage(repository=u'clusterhq/flocker',
                              tag=u'release-14.0')
        )

        result1 = api.start_container(application=application)
        self.successResultOf(result1)

        result2 = api.start_container(application=application)
        self.failureResultOf(result2, AlreadyExists)


class DeployerStopContainerTests(SynchronousTestCase):
    """
    Tests for ``Deployer.stop_container``.
    """
    def test_stop(self):
        """
        ``Deployer.stop_container`` accepts an application object and returns
        a deferred which fires when the `gear` unit has been removed.
        """
        fake_gear = FakeGearClient()
        api = Deployer(gear_client=fake_gear)
        application = Application(
            name=b'site-example.com',
            image=DockerImage(repository=u'clusterhq/flocker',
                              tag=u'release-14.0')
        )

        api.start_container(application=application)
        existed = fake_gear.exists(application.name)
        stop_result = api.stop_container(application=application)
        exists_result = fake_gear.exists(unit_name=application.name)

        self.assertEqual(
            (None, True, False),
            (self.successResultOf(stop_result),
             self.successResultOf(existed),
             self.successResultOf(exists_result))
        )

    def test_does_not_exist(self):
        """
        ``Deployer.stop_container`` does not errback if the application does
        not exist.
        """
        api = Deployer(gear_client=FakeGearClient())
        application = Application(
            name=b'site-example.com',
            image=DockerImage(repository=u'clusterhq/flocker',
                              tag=u'release-14.0')
        )
        result = api.stop_container(application=application)
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
        api = Deployer(gear_client=fake_gear)
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
        api = Deployer(gear_client=fake_gear)
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
        api = Deployer(gear_client=fake_gear)
        d = api.discover_node_configuration()

        self.assertEqual(sorted(applications), sorted(self.successResultOf(d)))


class DeployerCalculateNecessaryStateChangesTests(SynchronousTestCase):
    """
    Tests for ``Deployer.calculate_necessary_state_changes``.
    """
    def test_no_applications(self):
        """
        ``Deployer.calculate_necessary_state_changes`` returns a ``Deferred``
        which fires with a :class:`StateChanges` instance indicating that no
        changes are necessary when there are no applications running or
        desired.
        """
        fake_gear = FakeGearClient(units={})
        api = Deployer(gear_client=fake_gear)
        desired = Deployment(nodes=frozenset())
        d = api.calculate_necessary_state_changes(desired_state=desired,
                                                  hostname=b'node.example.com')
        expected = StateChanges(containers_to_start=set(),
                                containers_to_stop=set())
        self.assertEqual(expected, self.successResultOf(d))

    def test_application_needs_stopping(self):
        """
        ``Deployer.calculate_necessary_state_changes`` specifies that an
        application must be stopped when it is running but not desired.
        """
        unit = Unit(name=u'site-example.com', activation_state=u'active')

        fake_gear = FakeGearClient(units={unit.name: unit})
        api = Deployer(gear_client=fake_gear)
        desired = Deployment(nodes=frozenset())
        d = api.calculate_necessary_state_changes(desired_state=desired,
                                                  hostname=b'node.example.com')
        to_stop = set([Application(name=unit.name)])
        expected = StateChanges(containers_to_start=set(),
                                containers_to_stop=to_stop)
        self.assertEqual(expected, self.successResultOf(d))

    def test_application_needs_starting(self):
        """
        ``Deployer.calculate_necessary_state_changes`` specifies that an
        application must be started when it is desired on the given node but
        not running.
        """
        fake_gear = FakeGearClient(units={})
        api = Deployer(gear_client=fake_gear)
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
                                                  hostname=b'node.example.com')
        expected = StateChanges(containers_to_start=set([application]),
                                containers_to_stop=set())
        self.assertEqual(expected, self.successResultOf(d))

    def test_only_this_node(self):
        """
        ``Deployer.calculate_necessary_state_changes`` does not specify that an
        application must be started if the desired changes apply to a different
        node.
        """
        fake_gear = FakeGearClient(units={})
        api = Deployer(gear_client=fake_gear)
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
                                                  hostname=b'node.example.com')
        expected = StateChanges(containers_to_start=set(),
                                containers_to_stop=set())
        self.assertEqual(expected, self.successResultOf(d))

    def test_no_change_needed(self):
        """
        ``Deployer.calculate_necessary_state_changes`` does not specify that an
        application must be started or stopped if the desired configuration
        is the same as the current configuration.
        """
        unit = Unit(name=u'mysql-hybridcluster', activation_state=u'active')

        fake_gear = FakeGearClient(units={unit.name: unit})
        api = Deployer(gear_client=fake_gear)

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
                                                  hostname=b'node.example.com')
        expected = StateChanges(containers_to_start=set(),
                                containers_to_stop=set())
        self.assertEqual(expected, self.successResultOf(d))

    def test_node_not_described(self):
        """
        ``Deployer.calculate_necessary_state_changes`` specifies that all
        applications on a node must be stopped if the desired configuration
        does not include that node.
        """
        unit = Unit(name=u'mysql-hybridcluster', activation_state=u'active')

        fake_gear = FakeGearClient(units={unit.name: unit})
        api = Deployer(gear_client=fake_gear)
        desired = Deployment(nodes=frozenset([]))
        d = api.calculate_necessary_state_changes(desired_state=desired,
                                                  hostname=b'node.example.com')
        to_stop = set([Application(name=unit.name)])
        expected = StateChanges(containers_to_start=set(),
                                containers_to_stop=to_stop)
        self.assertEqual(expected, self.successResultOf(d))


class DeployerChangeNodeStateTests(SynchronousTestCase):
    """
    Tests for ``Deployer.change_node_state``.
    """

    def test_containers_started(self):
        pass
