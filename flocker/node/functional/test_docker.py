# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Functional tests for :module:`flocker.node._docker`.
"""

from __future__ import absolute_import

import time
import socket
from functools import partial

from docker.errors import APIError
from docker import Client
# Docker-py uses 1.16 API by default, which isn't supported by docker, so force
# the use of the 1.15 API until we upgrade docker in flocker-dev
Client = partial(Client, version="1.15")

from twisted.trial.unittest import TestCase
from twisted.python.filepath import FilePath
from twisted.internet.defer import succeed, gatherResults
from twisted.internet.error import ConnectionRefusedError
from twisted.web.client import ResponseNeverReceived

from treq import request, content

from pyrsistent import pvector

from ...testtools import (
    loop_until, find_free_port, DockerImageBuilder, assertContainsAll,
    random_name)

from ..test.test_docker import make_idockerclient_tests
from .._docker import (
    DockerClient, PortMap, Environment, NamespacedDockerClient,
    BASE_NAMESPACE, Volume, AddressInUse,
)
from ...control._model import RestartNever, RestartAlways, RestartOnFailure
from ..testtools import if_docker_configured, wait_for_unit_state


def namespace_for_test(test_case):
    return u"ns-" + random_name(test_case)


class IDockerClientTests(make_idockerclient_tests(
        lambda test_case: DockerClient(
            namespace=namespace_for_test(test_case)
        ),
)):
    """
    ``IDockerClient`` tests for ``DockerClient``.
    """
    @if_docker_configured
    def setUp(self):
        pass


class IDockerClientNamespacedTests(make_idockerclient_tests(
        lambda test_case: NamespacedDockerClient(
            namespace=namespace_for_test(test_case)
        )
)):
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
    clientException = APIError

    @if_docker_configured
    def setUp(self):
        self.namespacing_prefix = namespace_for_test(self)

    def make_client(self):
        return DockerClient(namespace=self.namespacing_prefix)

    def create_container(self, client, name, image):
        """
        Create (but don't start) a container via the supplied client.

        :param DockerClient client: The Docker API client.
        :param unicode name: The container name.
        :param unicode image: The image name.
        """
        container_name = client._to_container_name(name)
        client._client.create_container(
            name=container_name, image=image)

    def start_container(self, unit_name,
                        image_name=u"openshift/busybox-http-app",
                        ports=None, expected_states=(u'active',),
                        environment=None, volumes=(),
                        mem_limit=None, cpu_shares=None,
                        restart_policy=RestartNever(),
                        command_line=None):
        """
        Start a unit and wait until it reaches the `active` state or the
        supplied `expected_state`.

        :param unicode unit_name: See ``IDockerClient.add``.
        :param unicode image_name: See ``IDockerClient.add``.
        :param list ports: See ``IDockerClient.add``.
        :param expected_states: A sequence of activation states to wait for.
        :param environment: See ``IDockerClient.add``.
        :param volumes: See ``IDockerClient.add``.
        :param mem_limit: See ``IDockerClient.add``.
        :param cpu_shares: See ``IDockerClient.add``.
        :param restart_policy: See ``IDockerClient.add``.
        :param command_line: See ``IDockerClient.add``.

        :return: ``Deferred`` that fires with the ``DockerClient`` when
            the unit reaches the expected state.
        """
        client = self.make_client()
        d = client.add(
            unit_name=unit_name,
            image_name=image_name,
            ports=ports,
            environment=environment,
            volumes=volumes,
            mem_limit=mem_limit,
            cpu_shares=cpu_shares,
            restart_policy=restart_policy,
            command_line=command_line,
        )
        self.addCleanup(client.remove, unit_name)

        d.addCallback(lambda _: wait_for_unit_state(client, unit_name,
                                                    expected_states))
        d.addCallback(lambda _: client)

        return d

    def test_default_base_url(self):
        """
        ``DockerClient`` instantiated with a default base URL for a socket
        connection has a client HTTP url after the connection is made.
        """
        client = DockerClient()
        self.assertEqual(client._client.base_url,
                         u'http+unix://var/run/docker.sock')

    def test_custom_base_url_tcp_http(self):
        """
        ``DockerClient`` instantiated with a custom base URL for a TCP
        connection has a client HTTP url after the connection is made.
        """
        client = DockerClient(base_url=b"tcp://127.0.0.1:2375")
        self.assertEqual(client._client.base_url, b"http://127.0.0.1:2375")

    def test_add_starts_container(self):
        """
        ``DockerClient.add`` starts the container.
        """
        name = random_name(self)
        return self.start_container(name)

    def test_correct_image_used(self):
        """
        ``DockerClient.add`` creates a container with the specified image.
        """
        name = random_name(self)
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
        d = client.add(u"!!!###!!!", u"busybox:latest")
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
        name = random_name(self)
        d = self.start_container(unit_name=name, image_name="busybox:latest",
                                 expected_states=(u'inactive',))
        return d

    def test_list_with_missing_image(self):
        """
        ``DockerClient.list()`` can list containers whose image is missing.

        The resulting output may be inaccurate, but that's OK: this only
        happens for non-running containers, who at worst we're going to
        restart anyway.
        """
        path = FilePath(self.mktemp())
        path.makedirs()
        path.child(b"Dockerfile.in").setContent(
            b"FROM busybox\nCMD /bin/true\n")
        builder = DockerImageBuilder(test=self, source_dir=path, cleanup=False)
        d = builder.build()

        def image_built(image_name):
            name = random_name(self)
            d = self.start_container(
                unit_name=name, image_name=image_name,
                expected_states=(u'inactive',))
            return d.addCallback(lambda ignored: (name, image_name))
        d.addCallback(image_built)

        def stopped_container_exists((name, image_name)):
            # Remove the image:
            docker_client = Client()
            docker_client.remove_image(image_name, force=True)

            # Should be able to still list the container:
            client = self.make_client()
            listed = client.list()
            listed.addCallback(lambda results: self.assertIn(
                (name, "inactive"),
                [(unit.name, unit.activation_state) for unit in results]))
            return listed
        d.addCallback(stopped_container_exists)

        return d

    def test_dead_is_removed(self):
        """
        ``DockerClient.remove()`` removes dead units without error.

        We use a `busybox` image here, because it will exit immediately and
        reach an `inactive` substate of `dead`.
        """
        name = random_name(self)
        d = self.start_container(unit_name=name, image_name="busybox:latest",
                                 expected_states=(u'inactive',))

        def remove_container(client):
            client.remove(name)
        d.addCallback(remove_container)
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

    def test_non_docker_port_collision(self):
        """
        ``DockerClient.add`` returns a ``Deferred`` that fails with
        ``AddressInUse`` if the external port of one of the ``PortMap``
        instances passed for ``ports`` is already in use on the system by
        something other than a Docker container.
        """
        address_user = socket.socket()
        self.addCleanup(address_user.close)

        address_user.bind(('', 0))
        used_address = address_user.getsockname()

        name = random_name(self)
        d = self.start_container(
            name, ports=[
                PortMap(internal_port=10000, external_port=used_address[1]),
            ],
        )
        return self.assertFailure(d, AddressInUse)

    def test_add_with_port(self):
        """
        ``DockerClient.add`` accepts a ports argument which is passed to
        Docker to expose those ports on the unit.

        Assert that the busybox-http-app returns the expected "Hello world!"
        response.

        XXX: We should use a stable internal container instead. See
        https://clusterhq.atlassian.net/browse/FLOC-120

        XXX: The busybox-http-app returns headers in the body of its response,
        hence this over complicated custom assertion. See
        https://github.com/openshift/geard/issues/213
        """
        expected_response = b'Hello world!\n'
        external_port = find_free_port()[1]
        name = random_name(self)
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

    def test_add_with_environment(self):
        """
        ``DockerClient.add`` accepts an environment object whose ID and
        variables are used when starting a docker image.
        """
        docker_dir = FilePath(self.mktemp())
        docker_dir.makedirs()
        docker_dir.child(b"Dockerfile").setContent(
            b'FROM busybox\n'
            b'CMD ["/bin/sh",  "-c", '
            b'"while true; do env && echo WOOT && sleep 1; done"]'
        )
        expected_variables = frozenset({
            'key1': 'value1',
            'key2': 'value2',
        }.items())
        unit_name = random_name(self)

        image = DockerImageBuilder(test=self, source_dir=docker_dir)
        d = image.build()

        def image_built(image_name):
            return self.start_container(
                unit_name=unit_name,
                image_name=image_name,
                environment=Environment(variables=expected_variables),
            )
        d.addCallback(image_built)

        def started(_):
            output = ""
            while True:
                output += Client().logs(self.namespacing_prefix + unit_name)
                if "WOOT" in output:
                    break
            assertContainsAll(
                output, test_case=self,
                needles=['{}={}\n'.format(k, v)
                         for k, v in expected_variables],
            )
        d.addCallback(started)
        return d

    def test_pull_image_if_necessary(self):
        """
        The Docker image is pulled if it is unavailable locally.
        """
        # Use an image that isn't likely to be in use by anything, since
        # it's old, and isn't used by other tests:
        image = u"busybox:ubuntu-12.04"
        # Make sure image is gone:
        docker = Client()
        try:
            docker.remove_image(image, force=True)
        except APIError as e:
            if e.response.status_code != 404:
                raise

        name = random_name(self)
        client = self.make_client()
        self.addCleanup(client.remove, name)
        d = client.add(name, image)
        d.addCallback(lambda _: self.assertTrue(docker.inspect_image(image)))
        return d

    def test_pull_timeout(self):
        """
        Pulling an image times-out if it takes longer than a provided timeout.
        """
        # Use an image that isn't likely to be in use by anything, since
        # it's old, and isn't used by other tests:
        image = u"ubuntu:12.04"
        # Make sure image is gone:
        docker = Client()
        try:
            docker.remove_image(image, force=True)
        except APIError as e:
            if e.response.status_code != 404:
                raise

        name = random_name(self)
        client = DockerClient(
            namespace=self.namespacing_prefix, long_timeout=1)
        self.addCleanup(client.remove, name)
        d = client.add(name, image)
        # requests has a TimeoutError, but timeout raises a ConnectionError.
        # Both are subclasses of IOError, so use that for now
        # https://github.com/kennethreitz/requests/issues/2620
        self.assertFailure(d, IOError)
        return d

    def test_pull_timeout_pull(self):
        """
        Image pull timeout does not affect subsequent pulls.
        """
        # Use an image that isn't likely to be in use by anything, since
        # it's old, and isn't used by other tests.  Note, this is the
        # same image as test_pull_image_if_necessary, but they run at
        # different times.
        image = u"busybox:ubuntu-12.04"
        # Make sure image is gone:
        docker = Client()
        try:
            docker.remove_image(image, force=True)
        except APIError as e:
            if e.response.status_code != 404:
                raise

        name = random_name(self)
        client = DockerClient(
            namespace=self.namespacing_prefix, long_timeout=1)
        self.addCleanup(client.remove, name)
        d = client.add(name, image)

        def unexpected_success(_):
            self.fail('Image unexpectedly pulled within timeout limit')

        def expected_failure(failure):
            self.assertIsNotNone(failure.check(IOError))
            # We got our failure, now try to successfully pull
            client = DockerClient(
                namespace=self.namespacing_prefix, long_timeout=600)
            return client.add(name, image)

        d.addCallbacks(unexpected_success, expected_failure)
        return d

    def test_namespacing(self):
        """
        Containers are created with a namespace prefixed to their container
        name.
        """
        docker = Client()
        name = random_name(self)
        client = self.make_client()
        self.addCleanup(client.remove, name)
        d = client.add(name, u"busybox:latest")

        def added(_):
            self.assertTrue(
                docker.inspect_container(self.namespacing_prefix + name))
        d.addCallback(added)
        return d

    def test_null_environment(self):
        """
        A container that does not include any environment variables contains
        an empty ``environment`` in the return ``Unit``.
        """
        docker_dir = FilePath(self.mktemp())
        docker_dir.makedirs()
        docker_dir.child(b"Dockerfile").setContent(
            b'FROM scratch\n'
            b'MAINTAINER info@clusterhq.com\n'
            b'CMD ["/bin/doesnotexist"]'
        )
        name = random_name(self)
        image = DockerImageBuilder(test=self, source_dir=docker_dir)
        d = image.build()

        def image_built(image_name):
            client = self.make_client()
            self.create_container(client, name, image_name)
            self.addCleanup(client.remove, name)
            return client.list()
        d.addCallback(image_built)

        def got_list(units):
            unit = [unit for unit in units if unit.name == name][0]
            self.assertIsNone(unit.environment)
        d.addCallback(got_list)
        return d

    def test_container_name(self):
        """
        The container name stored on returned ``Unit`` instances matches the
        expected container name.
        """
        client = self.make_client()
        name = random_name(self)
        self.addCleanup(client.remove, name)
        d = client.add(name, u"busybox:latest")
        d.addCallback(lambda _: client.list())

        def got_list(units):
            unit = [unit for unit in units if unit.name == name][0]
            self.assertEqual(unit.container_name,
                             self.namespacing_prefix + name)
        d.addCallback(got_list)
        return d

    def test_empty_environment(self):
        """
        When a container with no custom environment variables is launched via
        ``DockerClient.add`` the environment in the resulting ``Unit`` returned
        from ``DockerClient.list`` will ignore the default HOME and PATH
        environment variables, leaving the ``Unit`` with an Environment of
        None.
        """
        name = random_name(self)
        d = self.start_container(name)

        def started(client):
            deferred_units = client.list()

            def check_units(units):
                unit = [unit for unit in units if unit.name == name][0]
                self.assertIsNone(unit.environment)

            deferred_units.addCallback(check_units)
        d.addCallback(started)
        return d

    def test_list_only_custom_environment(self):
        """
        When a container containing custom environment variables is launched
        and the image used also injects environment variables, only the custom
        variables we injected are returned by ``DockerClient.list``, whereas
        variables set by the image are discarded.

        All Docker containers have a PATH environment variable. In addition,
        the openshift/busybox-http-app image contains an STI_SCRIPTS_URL
        environment variable. These are therefore disregarded the variables
        disregarded in this test, whereas our custom environment is listed in
        the returned Units.

        https://registry.hub.docker.com/u/openshift/busybox-http/dockerfile/
        """
        name = random_name(self)
        environment = {
            'my_variable': 'some value',
            'another_variable': '12345'
        }
        environment = frozenset(environment.items())
        d = self.start_container(
            name,
            environment=Environment(variables=environment)
        )

        def started(client):
            deferred_units = client.list()

            def check_units(units):
                unit = [unit for unit in units if unit.name == name][0]
                expected = Environment(variables=environment)
                self.assertEqual(unit.environment, expected)

            deferred_units.addCallback(check_units)

        d.addCallback(started)
        return d

    def test_add_with_volumes(self):
        """
        ``DockerClient.add`` accepts a list of ``Volume`` instances which are
        mounted within the container.
        """
        docker_dir = FilePath(self.mktemp())
        docker_dir.makedirs()
        docker_dir.child(b"Dockerfile").setContent(
            b'FROM busybox\n'
            b'CMD ["/bin/sh",  "-c", '
            b'"touch /mnt1/a; touch /mnt2/b"]'
        )
        image = DockerImageBuilder(test=self, source_dir=docker_dir)
        d = image.build()

        def image_built(image_name):
            unit_name = random_name(self)

            path1 = FilePath(self.mktemp())
            path1.makedirs()
            path2 = FilePath(self.mktemp())
            path2.makedirs()

            d = self.start_container(
                unit_name=unit_name,
                image_name=image_name,
                volumes=[
                    Volume(node_path=path1, container_path=FilePath(b"/mnt1")),
                    Volume(
                        node_path=path2, container_path=FilePath(b"/mnt2"))],
                expected_states=(u'inactive',),
            )
            return d.addCallback(lambda _: (path1, path2))
        d.addCallback(image_built)

        def started((path1, path2)):
            expected1 = path1.child(b"a")
            expected2 = path2.child(b"b")
            for i in range(100):
                if expected1.exists() and expected2.exists():
                    return
                else:
                    time.sleep(0.1)
            self.fail("Files never created.")
        return d.addCallback(started)

    def test_add_with_memory_limit(self):
        """
        ``DockerClient.add`` accepts an integer mem_limit parameter which is
        passed to Docker when creating a container as the maximum amount of RAM
        available to that container.
        """
        MEMORY_100MB = 100000000
        name = random_name(self)
        d = self.start_container(name, mem_limit=MEMORY_100MB)

        def started(_):
            docker = Client()
            data = docker.inspect_container(self.namespacing_prefix + name)
            self.assertEqual(data[u"Config"][u"Memory"],
                             MEMORY_100MB)
        d.addCallback(started)
        return d

    def test_add_with_cpu_shares(self):
        """
        ``DockerClient.add`` accepts an integer cpu_shares parameter which is
        passed to Docker when creating a container as the CPU shares weight
        for that container. This is a relative weight for CPU time versus other
        containers and does not directly constrain CPU usage, i.e. a CPU share
        constrained container can still use 100% CPU if other containers are
        idle. Default shares when unspecified is 1024.
        """
        name = random_name(self)
        d = self.start_container(name, cpu_shares=512)

        def started(_):
            docker = Client()
            data = docker.inspect_container(self.namespacing_prefix + name)
            self.assertEqual(data[u"Config"][u"CpuShares"], 512)
        d.addCallback(started)
        return d

    def test_add_without_cpu_or_mem_limits(self):
        """
        ``DockerClient.add`` when creating a container with no mem_limit or
        cpu_shares specified will create a container without these resource
        limits, returning integer 0 as the values for Memory and CpuShares from
        its API when inspecting such a container.
        """
        name = random_name(self)
        d = self.start_container(name)

        def started(_):
            docker = Client()
            data = docker.inspect_container(self.namespacing_prefix + name)
            self.assertEqual(data[u"Config"][u"Memory"], 0)
            self.assertEqual(data[u"Config"][u"CpuShares"], 0)
        d.addCallback(started)
        return d

    def start_restart_policy_container(self, mode, restart_policy):
        """
        Start a container for testing restart policies.

        :param unicode mode: Mode of container. One of
            - ``"failure"``: The container will always exit with a failure.
            - ``"success-then-sleep"``: The container will exit with success
              once, then sleep forever.
            - ``"failure-then-sucess"``: The container will exit with failure
              once, then with failure.
        :param IRestartPolicy restart_policy: The restart policy to use for
            the container.

        :returns Deferred: A deferred that fires with the number of times the
            container was started.
        """
        docker_dir = FilePath(__file__).sibling('retry-docker')
        name = random_name(self)
        data = FilePath(self.mktemp())
        data.makedirs()
        count = data.child('count')
        count.setContent("0")
        marker = data.child('marker')

        image = DockerImageBuilder(test=self, source_dir=docker_dir)
        d = image.build()

        def image_built(image_name):
            if mode == u"success-then-sleep":
                expected_states = (u'active',)
            else:
                expected_states = (u'inactive',)

            return self.start_container(
                name, image_name=image_name,
                restart_policy=restart_policy,
                environment=Environment(variables={u'mode': mode}),
                volumes=[
                    Volume(node_path=data, container_path=FilePath(b"/data"))],
                expected_states=expected_states)
        d.addCallback(image_built)

        if mode == u"success-then-sleep":
            # TODO: if the `run` script fails for any reason,
            # then this will loop forever.

            # TODO: use the "wait for predicate" helper
            def wait_for_marker(_):
                while not marker.exists():
                    time.sleep(0.01)
            d.addCallback(wait_for_marker)

        d.addCallback(lambda ignored: count.getContent())
        return d

    def test_restart_policy_never(self):
        """
        An container with a restart policy of never isn't restarted
        after it exits.
        """
        d = self.start_restart_policy_container(
            mode=u"failure", restart_policy=RestartNever())

        d.addCallback(self.assertEqual, "1")
        return d

    def test_restart_policy_always(self):
        """
        An container with a restart policy of always is restarted
        after it exits.
        """
        d = self.start_restart_policy_container(
            mode=u"success-then-sleep", restart_policy=RestartAlways())

        d.addCallback(self.assertEqual, "2")
        return d

    def test_restart_policy_on_failure(self):
        """
        An container with a restart policy of on-failure is restarted
        after it exits with a non-zero result.
        """
        d = self.start_restart_policy_container(
            mode=u"failure-then-success", restart_policy=RestartOnFailure())

        d.addCallback(self.assertEqual, "2")
        return d

    def test_restart_policy_on_failure_maximum_count(self):
        """
        A container with a restart policy of on-failure and a maximum
        retry count is not restarted if it fails as many times than the
        specified maximum.
        """
        d = self.start_restart_policy_container(
            mode=u"failure",
            restart_policy=RestartOnFailure(maximum_retry_count=5))

        # A Docker change e721ed9b5319e8e7c1daf87c34690f8a4e62c9e3 means that
        # this value depends on the version of Docker.
        d.addCallback(self.assertIn, ("5", "6"))
        return d

    def test_command_line(self):
        """
        A container with custom command line is run with those arguments.
        """
        external_port = find_free_port()[1]
        name = random_name(self)
        d = self.start_container(
            name, image_name=u"busybox",
            # Pass in pvector since this likely to be what caller actually
            # passes in:
            command_line=pvector([u"sh", u"-c", u"""\
echo -n '#!/bin/sh
echo -n "HTTP/1.1 200 OK\r\n\r\nhi"
' > /tmp/script.sh;
chmod +x /tmp/script.sh;
nc -ll -p 8080 -e /tmp/script.sh
"""]),
            ports=[PortMap(internal_port=8080,
                           external_port=external_port)])

        d.addCallback(
            lambda ignored: self.request_until_response(external_port))

        def started(response):
            d = content(response)
            d.addCallback(lambda body: self.assertEqual(b"hi", body))
            return d
        d.addCallback(started)
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
        name = random_name(self)
        client = DockerClient()
        self.addCleanup(client.remove, name)
        d = client.add(name, u"busybox:latest")
        d.addCallback(lambda _: self.assertTrue(
            docker.inspect_container(u"flocker--" + name)))
        return d

    def test_list_removed_containers(self):
        """
        ``DockerClient.list`` does not list containers which are removed,
        during its operation, from another thread.
        """
        namespace = namespace_for_test(self)
        flocker_docker_client = DockerClient(namespace=namespace)

        name1 = random_name(self)
        adding_unit1 = flocker_docker_client.add(
            name1, u'openshift/busybox-http-app')
        self.addCleanup(flocker_docker_client.remove, name1)

        name2 = random_name(self)
        adding_unit2 = flocker_docker_client.add(
            name2, u'openshift/busybox-http-app')
        self.addCleanup(flocker_docker_client.remove, name2)

        docker_client = flocker_docker_client._client
        docker_client_containers = docker_client.containers

        def simulate_missing_containers(*args, **kwargs):
            """
            Remove a container before returning the original list.
            """
            containers = docker_client_containers(*args, **kwargs)
            container_name1 = flocker_docker_client._to_container_name(name1)
            docker_client.remove_container(
                container=container_name1, force=True)
            return containers

        adding_units = gatherResults([adding_unit1, adding_unit2])
        patches = []

        def get_list(ignored):
            patch = self.patch(
                docker_client,
                'containers',
                simulate_missing_containers
            )
            patches.append(patch)
            return flocker_docker_client.list()

        listing_units = adding_units.addCallback(get_list)

        def check_list(units):
            for patch in patches:
                patch.restore()
            self.assertEqual(
                [name2], sorted([unit.name for unit in units])
            )
        running_assertions = listing_units.addCallback(check_list)

        return running_assertions

    def error_passthrough_test(self, method_name):
        """
        If the given method name on the underyling ``Docker`` client has a
        non-404 error, that gets passed through to ``Docker.list()``.

        :param str method_name: Method of a docker ``Client``.
        :return: ``Deferred`` firing on test success.
        """
        name = random_name(self)
        client = DockerClient()
        self.addCleanup(client.remove, name)
        d = client.add(name, u"busybox:latest")

        class Response(object):
            status_code = 500
            content = ""

        def error(name):
            raise APIError("", Response())

        def added(_):
            # Monekypatch cause triggering non-404 errors from
            # inspect_container is hard.
            self.patch(client._client, method_name, error)
            return client.list()
        d.addCallback(added)
        return self.assertFailure(d, APIError)

    def test_list_error_inspecting_container(self):
        """
        If an error occurs inspecting a container it is passed through.
        """
        return self.error_passthrough_test("inspect_container")

    def test_list_error_inspecting_image(self):
        """
        If an error occurs inspecting an image it is passed through.
        """
        return self.error_passthrough_test("inspect_image")


class NamespacedDockerClientTests(GenericDockerClientTests):
    """
    Functional tests for ``NamespacedDockerClient``.
    """
    @if_docker_configured
    def setUp(self):
        self.namespace = namespace_for_test(self)
        self.namespacing_prefix = BASE_NAMESPACE + self.namespace + u"--"

    def make_client(self):
        return NamespacedDockerClient(self.namespace)

    def create_container(self, client, name, image):
        """
        Create (but don't start) a container via the supplied client.

        :param DockerClient client: The Docker API client.
        :param unicode name: The container name.
        :param unicode image: The image name.
        """
        container_name = client._client._to_container_name(name)
        client._client._client.create_container(
            name=container_name, image=image)

    def test_isolated_namespaces(self):
        """
        Containers in one namespace are not visible in another namespace.
        """
        client = NamespacedDockerClient(namespace=namespace_for_test(self))
        client2 = NamespacedDockerClient(namespace=namespace_for_test(self))
        name = random_name(self)

        self.addCleanup(client.remove, name)
        d = client.add(name, u"busybox:latest")
        d.addCallback(lambda _: client2.list())
        d.addCallback(self.assertEqual, set())
        return d
