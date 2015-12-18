# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for :module:`flocker.node._docker`.
"""

from zope.interface.verify import verifyObject

from pyrsistent import pset, pvector

from docker.errors import APIError

from twisted.python.filepath import FilePath

from ...testtools import (
    AsyncTestCase, TestCase, random_name, make_with_init_tests,
)
from ..testtools import add_with_port_collision_retry

from .._docker import (
    IDockerClient, FakeDockerClient, AddressInUse, AlreadyExists, PortMap,
    Unit, Environment, Volume,
)

from ...control._model import RestartAlways, RestartNever, RestartOnFailure

# Just some image we can use to start a container.  No particularly behavior
# should be expected from this image except that it exists.
#
# Note we explicitly select the "latest" tag to avoid tripping over a Docker
# 1.8.1 / Docker hub interaction that results in pulls failing. See
# https://github.com/docker/docker/issues/15699
ANY_IMAGE = u"openshift/busybox-http-app:latest"


def make_idockerclient_tests(fixture):
    """
    Create a TestCase for IDockerClient.

    :param fixture: A fixture that returns a :class:`IDockerClient`
        provider.
    """
    class IDockerClientTests(AsyncTestCase):
        """
        Tests for :class:`IDockerClientTests`.

        These are functional tests if run against a real Docker daemon.
        """
        def test_interface(self):
            """The tested object provides :class:`IDockerClient`."""
            client = fixture(self)
            self.assertTrue(verifyObject(IDockerClient, client))

        def test_add_and_remove(self):
            """
            An added container can be removed without an error.
            """
            client = fixture(self)
            name = random_name(self)
            d = client.add(name, u"busybox")
            d.addCallback(lambda _: client.remove(name))
            return d

        def test_no_double_add(self):
            """
            Adding a container with name that already exists results in error.
            """
            client = fixture(self)
            name = random_name(self)
            self.addCleanup(client.remove, name)
            d = client.add(name, u"busybox")

            def added(_):
                return client.add(name, u"busybox")
            d.addCallback(added)
            d = self.assertFailure(d, AlreadyExists)
            d.addCallback(lambda exc: self.assertEqual(exc.args[0], name))
            return d

        def test_remove_nonexistent_is_ok(self):
            """
            Removing a non-existent container does not result in a error.
            """
            client = fixture(self)
            name = random_name(self)
            return client.remove(name)

        def test_double_remove_is_ok(self):
            """
            Removing a container twice in a row does not result in error.
            """
            client = fixture(self)
            name = random_name(self)
            d = client.add(name, u"busybox")
            d.addCallback(lambda _: client.remove(name))
            d.addCallback(lambda _: client.remove(name))
            return d

        def test_unknown_does_not_exist(self):
            """
            A container that was never added does not exist.
            """
            client = fixture(self)
            name = random_name(self)
            d = client.exists(name)
            d.addCallback(self.assertFalse)
            return d

        def test_added_exists(self):
            """
            An added container exists.
            """
            client = fixture(self)
            name = random_name(self)
            self.addCleanup(client.remove, name)
            d = client.add(name, u"busybox")

            def added(_):
                return client.exists(name)
            d.addCallback(added)
            d.addCallback(self.assertTrue)
            return d

        def test_removed_does_not_exist(self):
            """
            A removed container does not exist.
            """
            client = fixture(self)
            name = random_name(self)
            d = client.add(name, ANY_IMAGE)
            d.addCallback(lambda _: client.remove(name))
            d.addCallback(lambda _: client.exists(name))
            d.addCallback(self.assertFalse)
            return d

        def test_zero_port_randomly_assigned(self):
            """
            If an external port number is given as 0, a random available port
            number is used.
            """
            client = fixture(self)
            name = random_name(self)
            portmap = PortMap(
                internal_port=1234, external_port=0,
            )
            self.addCleanup(client.remove, name)
            d = client.add(name, ANY_IMAGE, ports=(portmap,))
            d.addCallback(lambda ignored: client.list())

            def check_port(units):
                portmap = list(list(units)[0].ports)[0]
                self.assertTrue(
                    0 < portmap.external_port < 2 ** 16,
                    "Unexpected automatic port assignment: {}".format(
                        portmap.external_port
                    ),
                )
            d.addCallback(check_port)
            return d

        def test_port_collision_raises_addressinuse(self):
            """
            If the container is configured with an external port number which
            is already in use, ``AddressInUse`` is raised.
            """
            client = fixture(self)
            name = random_name(self)
            portmap = PortMap(
                internal_port=12345, external_port=0,
            )
            self.addCleanup(client.remove, name)
            d = client.add(name, ANY_IMAGE, ports=(portmap,))
            d.addCallback(lambda ignored: client.list())

            def extract_port(units):
                return list(list(units)[0].ports)[0].external_port
            d.addCallback(extract_port)

            def collide(external_port):
                self.external_port = external_port
                portmap = PortMap(
                    internal_port=54321, external_port=external_port,
                )
                name = random_name(self)
                self.addCleanup(client.remove, name)
                return client.add(name, ANY_IMAGE, ports=(portmap,))
            d.addCallback(collide)
            d = self.assertFailure(d, AddressInUse)

            def failed(exception):
                self.assertEqual(
                    exception.address, (b"0.0.0.0", self.external_port)
                )
                self.assertIsInstance(exception.apierror, APIError)
            d.addCallback(failed)
            return d

        def test_added_is_listed(self):
            """
            An added container is included in the output of ``list()``.
            """
            client = fixture(self)
            name = random_name(self)
            image = ANY_IMAGE

            portmaps = [
                PortMap(internal_port=80, external_port=0),
                PortMap(internal_port=5432, external_port=0),
            ]
            volumes = (
                Volume(node_path=FilePath(self.mktemp()),
                       container_path=FilePath(b'/var/lib/data')),
            )
            environment = (
                (u'CUSTOM_ENV_A', u'a value'),
                (u'CUSTOM_ENV_B', u'another value'),
            )
            environment = Environment(variables=frozenset(environment))
            self.addCleanup(client.remove, name)

            d = add_with_port_collision_retry(
                client,
                name,
                image_name=image,
                ports=portmaps,
                volumes=volumes,
                environment=environment,
                mem_limit=100000000,
                cpu_shares=512,
                restart_policy=RestartAlways(),
            )

            def added((app, portmaps)):
                d = client.list()
                d.addCallback(lambda units: (units, portmaps))
                return d
            d.addCallback(added)

            def got_list((units, portmaps)):
                result = units.pop()

                expected = Unit(
                    name=name, container_name=name, activation_state=u"active",
                    container_image=image, ports=frozenset(portmaps),
                    environment=environment, volumes=frozenset(volumes),
                    mem_limit=100000000, cpu_shares=512,
                    restart_policy=RestartAlways(),
                )

                # This test is not concerned with a returned ``Unit``'s
                # ``container_name`` and unlike other properties of the
                # result, does not expect ``container_name`` to be any
                # particular value. Manually setting it below to a fixed
                # known value simply allows us to compare an entire Unit
                # object instead of individual properties and is therefore
                # a convenience measure.
                result = result.set("container_name", name)
                self.assertEqual(result, expected)
            d.addCallback(got_list)
            return d

        def test_removed_is_not_listed(self):
            """
            A removed container is not included in the output of ``list()``.
            """
            client = fixture(self)
            name = random_name(self)

            d = client.add(name, ANY_IMAGE)
            d.addCallback(lambda _: client.remove(name))
            d.addCallback(lambda _: client.list())

            def got_list(units):
                self.assertNotIn(name, [unit.name for unit in units])
            d.addCallback(got_list)
            return d

        def test_container_name(self):
            """
            Each container also records the container name twice.
            """
            # This is silly behavior.  Get rid of it when fixing
            # <https://clusterhq.atlassian.net/browse/FLOC-819>.
            client = fixture(self)
            name = random_name(self)
            self.addCleanup(client.remove, name)
            d = client.add(name, u"busybox")
            d.addCallback(lambda _: client.list())

            def got_list(units):
                unit = [unit for unit in units if unit.name == name][0]
                self.assertIsInstance(unit.container_name, unicode)
            d.addCallback(got_list)
            return d

        def test_command_line(self):
            """
            Containers created with a command-line have a command-line included
            when listed.
            """
            client = fixture(self)
            name = random_name(self)
            self.addCleanup(client.remove, name)
            command_line = [u"nc", u"-l", u"-p", u"1234"]
            d = client.add(name, u"busybox", command_line=command_line)
            d.addCallback(lambda _: client.list())

            def got_list(units):
                unit = [unit for unit in units if unit.name == name][0]
                self.assertEqual(unit.command_line, pvector(command_line))
            d.addCallback(got_list)
            return d

        def assert_restart_policy_round_trips(self, restart_policy):
            """
            Creating a container with the given restart policy creates a
            container that reports that same policy.

            :param IRestartPolicy restart_policy: The restart policy to test.
            """
            client = fixture(self)
            name = random_name(self)
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
        make_idockerclient_tests(
            fixture=lambda test_case: FakeDockerClient(),
        )
):
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
                ports=pset((PortMap(internal_port=80, external_port=8080),)),
                environment=Environment(variables={u'foo': u'bar'}),
                restart_policy=RestartAlways(),
            ),
            expected_defaults=dict(
                ports=pset(), container_image=None, environment=None,
                restart_policy=RestartNever())
        )
):
    """
    Tests for ``Unit.__init__``.
    """


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
