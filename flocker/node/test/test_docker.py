# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""Tests for :module:`flocker.node._docker`."""

from zope.interface.verify import verifyObject

from twisted.trial.unittest import TestCase
from twisted.python.filepath import FilePath

from ...testtools import random_name, make_with_init_tests
from .._docker import (
    IDockerClient, FakeDockerClient, AlreadyExists, PortMap, Unit,
    Environment, Volume)

from ...control._model import RestartAlways, RestartNever, RestartOnFailure


def make_idockerclient_tests(fixture):
    """
    Create a TestCase for IDockerClient.

    :param fixture: A fixture that returns a :class:`IDockerClient`
        provider.
    """
    class IDockerClientTests(TestCase):
        """
        Tests for :class:`IDockerClientTests`.

        These are functional tests if run against a real Docker daemon.
        """
        def test_interface(self):
            """The tested object provides :class:`IDockerClient`."""
            client = fixture(self)
            self.assertTrue(verifyObject(IDockerClient, client))

        def test_add_and_remove(self):
            """An added unit can be removed without an error."""
            client = fixture(self)
            name = random_name()
            d = client.add(name, u"busybox")
            d.addCallback(lambda _: client.remove(name))
            return d

        def test_no_double_add(self):
            """Adding a unit with name that already exists results in error."""
            client = fixture(self)
            name = random_name()
            d = client.add(name, u"busybox")

            def added(_):
                self.addCleanup(client.remove, name)
                return client.add(name, u"busybox")
            d.addCallback(added)
            d = self.assertFailure(d, AlreadyExists)
            d.addCallback(lambda exc: self.assertEqual(exc.args[0], name))
            return d

        def test_remove_nonexistent_is_ok(self):
            """Removing a non-existent unit does not result in a error."""
            client = fixture(self)
            name = random_name()
            return client.remove(name)

        def test_double_remove_is_ok(self):
            """Removing a unit twice in a row does not result in error."""
            client = fixture(self)
            name = random_name()
            d = client.add(name, u"busybox")
            d.addCallback(lambda _: client.remove(name))
            d.addCallback(lambda _: client.remove(name))
            return d

        def test_unknown_does_not_exist(self):
            """A unit that was never added does not exist."""
            client = fixture(self)
            name = random_name()
            d = client.exists(name)
            d.addCallback(self.assertFalse)
            return d

        def test_added_exists(self):
            """An added unit exists."""
            client = fixture(self)
            name = random_name()
            d = client.add(name, u"busybox")

            def added(_):
                self.addCleanup(client.remove, name)
                return client.exists(name)
            d.addCallback(added)
            d.addCallback(self.assertTrue)
            return d

        def test_removed_does_not_exist(self):
            """A removed unit does not exist."""
            client = fixture(self)
            name = random_name()
            d = client.add(name, u"openshift/busybox-http-app")
            d.addCallback(lambda _: client.remove(name))
            d.addCallback(lambda _: client.exists(name))
            d.addCallback(self.assertFalse)
            return d

        def test_added_is_listed(self):
            """An added unit is included in the output of ``list()``."""
            client = fixture(self)
            name = random_name()
            image = u"openshift/busybox-http-app"
            portmaps = (
                PortMap(internal_port=80, external_port=8080),
                PortMap(internal_port=5432, external_port=5432)
            )
            volumes = (
                Volume(node_path=FilePath(b'/tmp'),
                       container_path=FilePath(b'/var/lib/data')),
            )
            self.addCleanup(client.remove, name)
            d = client.add(
                name,
                image,
                ports=portmaps,
                volumes=volumes,
                mem_limit=100000000,
                cpu_shares=512,
                restart_policy=RestartAlways(),
            )
            d.addCallback(lambda _: client.list())

            expected = Unit(
                name=name, container_name=name, activation_state=u"active",
                container_image=image, ports=frozenset(portmaps),
                environment=None, volumes=frozenset(volumes),
                mem_limit=100000000, cpu_shares=512,
                restart_policy=RestartAlways(),
            )

            def got_list(units):
                result = units.pop()
                # This test is not concerned with a returned ``Unit``'s
                # ``container_name`` and unlike other properties of the
                # result, does not expect ``container_name`` to be any
                # particular value. Manually setting it below to a fixed
                # known value simply allows us to compare an entire Unit
                # object instead of individual properties and is therefore
                # a convenience measure.
                result.container_name = name
                self.assertEqual(result, expected)
            d.addCallback(got_list)
            return d

        def test_removed_is_not_listed(self):
            """A removed unit is not included in the output of ``list()``."""
            client = fixture(self)
            name = random_name()

            d = client.add(name, u"openshift/busybox-http-app")
            d.addCallback(lambda _: client.remove(name))
            d.addCallback(lambda _: client.list())

            def got_list(units):
                self.assertNotIn(name, [unit.name for unit in units])
            d.addCallback(got_list)
            return d

        def test_container_name(self):
            """
            Each unit also records the name of the container it is running in.
            """
            client = fixture(self)
            name = random_name()
            self.addCleanup(client.remove, name)
            d = client.add(name, u"busybox")
            d.addCallback(lambda _: client.list())

            def got_list(units):
                unit = [unit for unit in units if unit.name == name][0]
                self.assertIsInstance(unit.container_name, unicode)
            d.addCallback(got_list)
            return d

        def assert_restart_policy_round_trips(self, restart_policy):
            """
            Creating a container with the given restart policy creates a
            container that reports that same policy.

            :param IRestartPolicy restart_policy: The restart policy to test.
            """
            client = fixture(self)
            name = random_name()
            self.addCleanup(client.remove, name)
            d = client.add(name, u"busybox", restart_policy=restart_policy)
            d.addCallback(lambda _: client.list())

            def got_list(units):
                unit = [unit for unit in units if unit.name == name][0]
                self.assertEqual(unit.restart_policy, restart_policy)
            d.addCallback(got_list)
            return d

        def test_add_with_restart_never(self):
            """
            ``DockerClient.add`` when creating a container with a restart
            policy, of never will create a container with this policy.
            """
            return self.assert_restart_policy_round_trips(RestartNever())

        def test_add_with_restart_always(self):
            """
            ``DockerClient.add`` when creating a container with a restart
            policy, of always will create a container with this policy.
            """
            return self.assert_restart_policy_round_trips(RestartAlways())

        def test_add_with_restart_on_failure(self):
            """
            ``DockerClient.add`` when creating a container with a restart
            policy, of on failure will create a container with this policy.
            """
            return self.assert_restart_policy_round_trips(RestartOnFailure())

        def test_add_with_restart_on_failure_with_maximum_retry(self):
            """
            ``DockerClient.add`` when creating a container with a restart
            policy, of on failure with a retry count will create a container
            with this policy.
            """
            return self.assert_restart_policy_round_trips(
                RestartOnFailure(maximum_retry_count=5))

    return IDockerClientTests


class FakeIDockerClientTests(
        make_idockerclient_tests(lambda t: FakeDockerClient())):
    """
    ``IDockerClient`` tests for ``FakeDockerClient``.
    """


class FakeDockerClientImplementationTests(TestCase):
    """
    Tests for implementation details of ``FakeDockerClient``.
    """
    def test_units_default(self):
        """
        ``FakeDockerClient._units`` is an empty dict by default.
        """
        self.assertEqual({}, FakeDockerClient()._units)

    def test_units_override(self):
        """
        ``FakeDockerClient._units`` can be supplied in the constructor.
        """
        units = {u'foo': Unit(name=u'foo', container_name=u'foo',
                              activation_state=u'active',
                              container_image=u'flocker/flocker:v1.0.0')}
        self.assertEqual(units, FakeDockerClient(units=units)._units)


class PortMapInitTests(
        make_with_init_tests(
            record_type=PortMap,
            kwargs=dict(
                internal_port=5678,
                external_port=910,
            )
        )
):
    """
    Tests for ``PortMap.__init__``.
    """


class PortMapTests(TestCase):
    """
    Tests for ``PortMap``.

    XXX: The equality tests in this case are incomplete. See
    https://github.com/hynek/characteristic/issues/4 for a proposed solution to
    this.
    """
    def test_repr(self):
        """
        ``PortMap.__repr__`` shows the internal and external ports.
        """
        self.assertEqual(
            "<PortMap(internal_port=5678, external_port=910)>",
            repr(PortMap(internal_port=5678, external_port=910))
        )

    def test_equal(self):
        """
        ``PortMap`` instances with the same internal and external ports compare
        equal.
        """
        self.assertEqual(
            PortMap(internal_port=5678, external_port=910),
            PortMap(internal_port=5678, external_port=910),
        )

    def test_not_equal(self):
        """
        ``PortMap`` instances with the different internal and external ports do
        not compare equal.
        """
        self.assertNotEqual(
            PortMap(internal_port=5678, external_port=910),
            PortMap(internal_port=1516, external_port=1718)
        )


class UnitInitTests(
        make_with_init_tests(
            record_type=Unit,
            kwargs=dict(
                name=u'site-example.com',
                container_name=u'flocker--site-example.com',
                activation_state=u'active',
                container_image=u'flocker/flocker:v1.0.0',
                ports=(PortMap(internal_port=80, external_port=8080),),
                environment=Environment(variables={u'foo': u'bar'}),
                restart_policy=RestartAlways(),
            ),
            expected_defaults=dict(
                ports=(), container_image=None, environment=None,
                restart_policy=RestartNever())
        )
):
    """
    Tests for ``Unit.__init__``.
    """


class UnitTests(TestCase):
    """
    Tests for ``Unit``.

    XXX: The equality tests in this case are incomplete. See
    https://github.com/hynek/characteristic/issues/4 for a proposed solution to
    this.
    """
    def test_repr(self):
        """
        ``Unit.__repr__`` shows the name, activation_state, container_image,
        and ports.
        """
        self.assertEqual(
            "<Unit(name=u'site-example.com', "
            "container_name=u'flocker--site-example.com', "
            "activation_state=u'active', "
            "container_image=u'flocker/flocker:v1.0.0', ports=[], "
            "environment=None, "
            "volumes=[<Volume(node_path=FilePath('/tmp'), "
            "container_path=FilePath('/blah'))>], "
            "mem_limit=None, cpu_shares=None, "
            "restart_policy=<RestartNever()>)>",

            repr(Unit(name=u'site-example.com',
                      container_name=u'flocker--site-example.com',
                      activation_state=u'active',
                      container_image=u'flocker/flocker:v1.0.0',
                      ports=[], environment=None,
                      volumes=[Volume(node_path=FilePath(b'/tmp'),
                                      container_path=FilePath(b'/blah'))])),
        )


class EnvironmentInitTests(
        make_with_init_tests(
            record_type=Environment,
            kwargs=dict(
                variables=dict(foo="bar"),
            ),
        )
):
    """
    Tests for ``Environment.__init__``.
    """


class EnvironmentTests(TestCase):
    """
    Tests for ``Environment``.
    """
    def test_to_dict(self):
        """
        ``Environment.to_dict`` returns a dictionary containing the
        the environment variables as key/value entries.
        """
        variables = {'baz': 'qux', 'foo': 'bar'}
        environment = Environment(variables=frozenset(variables.items()))

        self.assertEqual(environment.to_dict(), variables)

    def test_repr(self):
        """
        ``Environment.__repr__`` shows the id and variables.
        """
        self.assertEqual(
            "<Environment("
            "variables=frozenset([('foo', 'bar')]))>",
            repr(Environment(variables=frozenset(dict(foo="bar").items())))
        )


class VolumeInitTests(
        make_with_init_tests(
            record_type=Volume,
            kwargs=dict(
                node_path=FilePath(b"/tmp"),
                container_path=FilePath(b"/blah"),
            ),
        )
):
    """
    Tests for ``Volume.__init__``.
    """
