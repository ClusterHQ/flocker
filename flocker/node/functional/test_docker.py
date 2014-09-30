# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Functional tests for :module:`flocker.node._docker`.
"""

from __future__ import absolute_import

import os
from unittest import skipIf

from docker.errors import APIError
from docker import Client

from twisted.trial.unittest import TestCase
from twisted.python.filepath import FilePath
from twisted.internet.defer import succeed
from twisted.internet.error import ConnectionRefusedError
from twisted.web.client import ResponseNeverReceived

from treq import request, content

from ...testtools import (
    loop_until, find_free_port, DockerImageBuilder, assertContainsAll,
    random_name)

from ..test.test_docker import make_idockerclient_tests
from .._docker import (
    DockerClient, PortMap, Environment, NamespacedDockerClient,
    BASE_NAMESPACE)
from ..testtools import if_docker_configured, wait_for_unit_state


_if_root = skipIf(os.getuid() != 0, "Must run as root.")


class IDockerClientTests(make_idockerclient_tests(
        lambda test_case: DockerClient(namespace=random_name()))):
    """
    ``IDockerClient`` tests for ``DockerClient``.
    """
    @if_docker_configured
    def setUp(self):
        pass


class IDockerClientNamespacedTests(make_idockerclient_tests(
        lambda test_case: NamespacedDockerClient(random_name()))):
    """
    ``IDockerClient`` tests for ``NamespacedDockerClient``.
    """
    @if_docker_configured
    def setUp(self):
        pass


class GenericDockerClientTests(TestCase):
    """
    Functional tests for ``DockerClient`` and other clients that talk to
    real Docker.
    """
    @if_docker_configured
    def setUp(self):
        self.namespacing_prefix = u"%s-%s-%s--" % (self.__class__.__name__,
                                                   self.id(), random_name())
        self.namespacing_prefix = self.namespacing_prefix.replace(u".", u"-")

    clientException = APIError

    def make_client(self):
        # Some of the tests assume container name matches unit name, so we
        # disable namespacing for these tests.
        return DockerClient(namespace=self.namespacing_prefix)

    def start_container(self, unit_name,
                        image_name=u"openshift/busybox-http-app",
                        ports=None, expected_states=(u'active',),
                        environment=None):
        """
        Start a unit and wait until it reaches the `active` state or the
        supplied `expected_state`.

        :param unicode unit_name: See ``IDockerClient.add``.
        :param unicode image_name: See ``IDockerClient.add``.
        :param list ports: See ``IDockerClient.add``.
        :param Unit expected_states: A list of activation states to wait for.

        :return: ``Deferred`` that fires with the ``DockerClient`` when
            the unit reaches the expected state.
        """
        client = self.make_client()
        d = client.add(
            unit_name=unit_name,
            image_name=image_name,
            ports=ports,
            environment=environment,
        )
        self.addCleanup(client.remove, unit_name)

        d.addCallback(lambda _: wait_for_unit_state(client, unit_name,
                                                    expected_states))
        d.addCallback(lambda _: client)

        return d

    def test_add_starts_container(self):
        """``DockerClient.add`` starts the container."""
        name = random_name()
        return self.start_container(name)

    @_if_root
    def test_correct_image_used(self):
        """
        ``DockerClient.add`` creates a container with the specified image.
        """
        name = random_name()
        d = self.start_container(name)

        def started(_):
            docker = Client()
            data = docker.inspect_container(self.namespacing_prefix + name)
            self.assertEqual(data[u"Config"][u"Image"],
                             u"openshift/busybox-http-app")
        d.addCallback(started)
        return d

    def test_add_error(self):
        """
        ``DockerClient.add`` returns a ``Deferred`` that errbacks with
        ``APIError`` if response code is not a success response code.
        """
        client = self.make_client()
        # add() calls exists(), and we don't want exists() to be the one
        # failing since that's not the code path we're testing, so bypass
        # it:
        client.exists = lambda _: succeed(False)
        # Illegal container name should make Docker complain when we try to
        # install the container:
        d = client.add(u"!!!###!!!", u"busybox")
        return self.assertFailure(d, self.clientException)

    def test_dead_is_listed(self):
        """
        ``DockerClient.list()`` includes dead units.

        We use a `busybox` image here, because it will exit immediately and
        reach an `inactive` substate of `dead`.

        There are no assertions in this test, because it will fail with a
        timeout if the unit with that expected state is never listed or if that
        unit never reaches that state.
        """
        name = random_name()
        d = self.start_container(unit_name=name, image_name="busybox",
                                 expected_states=(u'inactive',))
        return d

    def request_until_response(self, port):
        """
        Resend a test HTTP request until a response is received.

        The container may have started, but the webserver inside may take a
        little while to start serving requests.

        :param int port: The localhost port to which an HTTP request will be
            sent.

        :return: A ``Deferred`` which fires with the result of the first
            successful HTTP request.
        """
        def send_request():
            """
            Send an HTTP request in a loop until the request is answered.
            """
            response = request(
                b"GET", b"http://127.0.0.1:%d" % (port,),
                persistent=False)

            def check_error(failure):
                """
                Catch ConnectionRefused errors and response timeouts and return
                False so that loop_until repeats the request.

                Other error conditions will be passed down the errback chain.
                """
                failure.trap(ConnectionRefusedError, ResponseNeverReceived)
                return False
            response.addErrback(check_error)
            return response

        return loop_until(send_request)

    def test_add_with_port(self):
        """
        ``DockerClient.add`` accepts a ports argument which is passed to
        Docker to expose those ports on the unit.

        Assert that the busybox-http-app returns the expected "Hello world!"
        response.

        XXX: We should use a stable internal container instead. See
        https://github.com/hybridlogic/flocker/issues/120

        XXX: The busybox-http-app returns headers in the body of its response,
        hence this over complicated custom assertion. See
        https://github.com/openshift/geard/issues/213
        """
        expected_response = b'Hello world!\n'
        external_port = find_free_port()[1]
        name = random_name()
        d = self.start_container(
            name, ports=[PortMap(internal_port=8080,
                                 external_port=external_port)])

        d.addCallback(
            lambda ignored: self.request_until_response(external_port))

        def started(response):
            d = content(response)
            d.addCallback(lambda body: self.assertIn(expected_response, body))
            return d
        d.addCallback(started)
        return d

    def build_slow_shutdown_image(self):
        """
        Create a Docker image that takes a while to shut down.

        This should really use Python instead of shell:
        https://github.com/ClusterHQ/flocker/issues/719

        :return: The name of created Docker image.
        """
        path = FilePath(self.mktemp())
        path.makedirs()
        path.child(b"Dockerfile.in").setContent("""\
FROM busybox
CMD sh -c "trap \"\" 2; sleep 3"
""")
        image = DockerImageBuilder(test=self, source_dir=path)
        return image.build()

    @_if_root
    def test_add_with_environment(self):
        """
        ``DockerClient.add`` accepts an environment object whose ID and
        variables are used when starting a docker image.
        """
        docker_dir = FilePath(self.mktemp())
        docker_dir.makedirs()
        docker_dir.child(b"Dockerfile").setContent(
            b'FROM busybox\n'
            b'CMD ["/bin/sh",  "-c", "while true; do env && sleep 1; done"]'
        )
        image = DockerImageBuilder(test=self, source_dir=docker_dir)
        image_name = image.build()
        unit_name = random_name()
        expected_variables = frozenset({
            'key1': 'value1',
            'key2': 'value2',
        }.items())
        d = self.start_container(
            unit_name=unit_name,
            image_name=image_name,
            environment=Environment(variables=expected_variables),
        )
        d.addCallback(lambda _: Client().logs(
            self.namespacing_prefix + unit_name))
        d.addCallback(
            assertContainsAll,
            test_case=self,
            needles=['{}={}\n'.format(k, v) for k, v in expected_variables],
        )
        return d

    def test_pull_image_if_necessary(self):
        """
        The Docker image is pulled if it is unavailable locally.
        """
        image = u"busybox"
        # Make sure image is gone:
        docker = Client()
        try:
            docker.remove_image(image)
        except APIError as e:
            if e.response.status_code != 404:
                raise

        name = random_name()
        client = self.make_client()
        self.addCleanup(client.remove, name)
        d = client.add(name, image)
        d.addCallback(lambda _: self.assertTrue(docker.inspect_image(image)))
        return d

    def test_namespacing(self):
        """
        Containers are created with a namespace prefixed to their container
        name.
        """
        docker = Client()
        name = random_name()
        client = self.make_client()
        self.addCleanup(client.remove, name)
        d = client.add(name, u"busybox")

        def added(_):
            self.assertTrue(
                docker.inspect_container(self.namespacing_prefix + name))
        d.addCallback(added)
        return d

    def test_container_name(self):
        """
        The container name stored on returned ``Unit`` instances matches the
        expected container name.
        """
        client = self.make_client()
        name = random_name()
        self.addCleanup(client.remove, name)
        d = client.add(name, u"busybox")
        d.addCallback(lambda _: client.list())

        def got_list(units):
            unit = [unit for unit in units if unit.name == name][0]
            self.assertEqual(unit.container_name,
                             self.namespacing_prefix + name)
        d.addCallback(got_list)
        return d


class DockerClientTests(TestCase):
    """
    Tests for ``DockerClient`` specifically.
    """
    @if_docker_configured
    def setUp(self):
        pass

    def test_default_namespace(self):
        """
        The default namespace is `u"flocker--"`.
        """
        docker = Client()
        name = random_name()
        client = DockerClient()
        self.addCleanup(client.remove, name)
        d = client.add(name, u"busybox")
        d.addCallback(lambda _: self.assertTrue(
            docker.inspect_container(u"flocker--" + name)))
        return d


class NamespacedDockerClientTests(GenericDockerClientTests):
    """
    Functional tests for ``NamespacedDockerClient``.
    """
    @if_docker_configured
    def setUp(self):
        self.namespace = u"%s-%s-%s" % (
            self.__class__.__name__, self.id(), random_name())
        self.namespace = self.namespace.replace(u".", u"-")
        self.namespacing_prefix = BASE_NAMESPACE + self.namespace + u"--"

    def make_client(self):
        return NamespacedDockerClient(self.namespace)

    def test_isolated_namespaces(self):
        """
        Containers in one namespace are not visible in another namespace.
        """
        client = NamespacedDockerClient(random_name())
        client2 = NamespacedDockerClient(random_name())
        name = random_name()

        d = client.add(name, u"busybox")
        self.addCleanup(client.remove, name)
        d.addCallback(lambda _: client2.list())
        d.addCallback(self.assertEqual, set())
        return d
