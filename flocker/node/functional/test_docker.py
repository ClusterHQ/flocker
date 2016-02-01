# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Functional tests for :module:`flocker.node._docker`.
"""

from __future__ import absolute_import

from datetime import timedelta
from functools import partial
import time
import socket

from eliot.testing import capture_logging, assertHasMessage

from requests.exceptions import ReadTimeout
from docker.errors import APIError

from twisted.python.monkey import MonkeyPatcher
from twisted.python.filepath import FilePath
from twisted.internet import reactor
from twisted.internet.defer import succeed, gatherResults
from twisted.internet.error import ConnectionRefusedError
from twisted.web.client import ResponseNeverReceived

from treq import request, content

from pyrsistent import PClass, pvector, field

from ...common import loop_until
from ...testtools import (
    find_free_port, flaky, DockerImageBuilder, assertContainsAll,
    random_name,
    async_runner, TestCase, AsyncTestCase,
)

from ..test.test_docker import ANY_IMAGE, make_idockerclient_tests
from .._docker import (
    DockerClient, PortMap, Environment, NamespacedDockerClient,
    BASE_NAMESPACE, Volume, AddressInUse, make_response,
    LOG_CACHED_IMAGE, dockerpy_client,
)
from ...control import (
    RestartNever, RestartAlways, RestartOnFailure, DockerImage
)
from ..testtools import (
    if_docker_configured, wait_for_unit_state, require_docker_version,
    add_with_port_collision_retry,
)


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
        super(IDockerClientTests, self).setUp()


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
        super(IDockerClientNamespacedTests, self).setUp()

    @flaky([u'FLOC-2628', u'FLOC-2874'])
    def test_added_is_listed(self):
        return super(IDockerClientNamespacedTests, self).test_added_is_listed()


class Registry(PClass):
    """
    Describe a Docker image registry.

    :ivar host: The IP address on which the registry is listening.
    :ivar port: The port number on which the registry is listening.
    :ivar name: The name of the container in which the registry is running.
    """
    host = field(mandatory=True, type=bytes, initial=b"127.0.0.1")
    port = field(mandatory=True, type=int)
    name = field(mandatory=True, type=unicode)

    @property
    def repository(self):
        """
        The string to use as an image name prefix to direct Docker to find that
        image in this registry instead of the default.
        """
        return "{host}:{port}".format(host=self.host, port=self.port)


class GenericDockerClientTests(AsyncTestCase):
    """
    Functional tests for ``DockerClient`` and other clients that talk to
    real Docker.
    """
    clientException = APIError

    # FLOC-3935: These tests (and the ones in NamespacedDockerClientTests) are
    # often timing out, sometimes in weird ways that cause interference with
    # other tests. Until we can identify the cause, effectively disable
    # timeouts on these tests and rely on the Jenkins timeout (or the limited
    # patience of developers) to ensure they halt.
    run_tests_with = async_runner(timeout=timedelta(hours=1))

    @if_docker_configured
    def setUp(self):
        super(GenericDockerClientTests, self).setUp()
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
                        image_name=u"openshift/busybox-http-app:latest",
                        ports=None, expected_states=(u'active',),
                        environment=None, volumes=(),
                        mem_limit=None, cpu_shares=None,
                        restart_policy=RestartNever(),
                        command_line=None,
                        retry_on_port_collision=False):
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

        if retry_on_port_collision:
            add = partial(add_with_port_collision_retry, client)
        else:
            add = client.add

        d = add(
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

        d.addCallback(lambda _: wait_for_unit_state(reactor, client, unit_name,
                                                    expected_states))
        d.addCallback(lambda _: client)

        return d

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
        image_name = u"openshift/busybox-http-app:latest"
        name = random_name(self)
        d = self.start_container(name, image_name=image_name)

        def started(_):
            docker = dockerpy_client()
            data = docker.inspect_container(self.namespacing_prefix + name)
            self.assertEqual(
                image_name,
                data[u"Config"][u"Image"],
            )
        d.addCallback(started)
        return d

    @capture_logging(assertHasMessage, LOG_CACHED_IMAGE)
    def test_list_image_data_cached(self, logger):
        """
        ``DockerClient.list`` will only an inspect an image ID once, caching
        the resulting data.
        """
        name = random_name(self)
        d = self.start_container(name, image_name=ANY_IMAGE)

        def started(client):
            listing = client.list()

            def listed(_):
                class FakeAPIError(Exception):
                    pass

                def fake_inspect_image(image):
                    raise FakeAPIError(
                        "Tried to inspect image {} twice.".format(image))
                # This is kind of nasty, but NamespacedDockerClient represents
                # its client via a proxying attribute.
                if isinstance(client, NamespacedDockerClient):
                    docker_client = client._client._client
                else:
                    docker_client = client._client
                self.patch(docker_client, "inspect_image", fake_inspect_image)
                # If image is not retrieved from the cache, list() here will
                # attempt to call inspect_image again, resulting in a call to
                # the fake_inspect_image function that will raise an exception.
                cached_listing = client.list()
                cached_listing.addCallback(lambda _: None)
                return cached_listing

            listing.addCallback(listed)
            return listing

        d.addCallback(started)
        return d

    @require_docker_version(
        '1.6.0',
        'This test uses the registry:2 image '
        'which requires Docker-1.6.0 or newer. '
        'See https://docs.docker.com/registry/deploying/ for details.'
    )
    def test_private_registry_image(self):
        """
        ``DockerClient.add`` can start containers based on an image from a
        private registry.

        A private registry is started in a container according to the
        instructions at:
         * https://docs.docker.com/registry/deploying/

        An image is pushed to that private registry and then a Flocker
        application is started that uses that private repository image name.

        Docker can pull from a private registry without any TLS configuration
        as long as it's running on the local host.
        """
        registry_listening = self.run_registry()

        def tag_and_push_image(registry):
            client = dockerpy_client()
            image_name = ANY_IMAGE
            # The image will normally have been pre-pulled on build slaves, but
            # may not already be available when running tests locally.
            client.pull(image_name)

            registry_image = self.push_to_registry(image_name, registry)

            # And the image will (hopefully) have been downloaded again from
            # the private registry in the next step, so cleanup that local
            # image once the test finishes.
            self.addCleanup(
                client.remove_image,
                image=registry_image.full_name
            )

            return registry_image

        pushing_image = registry_listening.addCallback(tag_and_push_image)

        def start_registry_image(registry_image):
            return self.start_container(
                unit_name=random_name(self),
                image_name=registry_image.full_name,
            )
        starting_registry_image = pushing_image.addCallback(
            start_registry_image
        )
        return starting_registry_image

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
            docker_client = dockerpy_client()
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

        return loop_until(reactor, send_request)

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
                                 external_port=external_port)],
            retry_on_port_collision=True,
        )

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
            client = dockerpy_client()
            while True:
                output += client.logs(self.namespacing_prefix + unit_name)
                if "WOOT" in output:
                    break
            assertContainsAll(
                output, test_case=self,
                needles=['{}={}\n'.format(k, v)
                         for k, v in expected_variables],
            )
        d.addCallback(started)
        return d

    @flaky(u"FLOC-3875")
    def test_pull_image_if_necessary(self):
        """
        The Docker image is pulled if it is unavailable locally.
        """
        client = dockerpy_client()

        path = FilePath(self.mktemp())
        path.makedirs()
        path.child(b"Dockerfile.in").setContent(
            b"FROM busybox\n"
            b"CMD /bin/true\n"
        )
        builder = DockerImageBuilder(
            test=self, source_dir=path,
            # We're going to manipulate the various tags on the image ourselves
            # in this test.  We'll do (the slightly more complicated) cleanup
            # so the builder shouldn't (and will encounter errors if we let
            # it).
            cleanup=False,
        )
        building = builder.build()
        registry_listening = self.run_registry()

        def create_container((image_name, registry)):
            registry_image = self.push_to_registry(image_name, registry)

            # And the image will (hopefully) have been downloaded again from
            # the private registry in the next step, so cleanup that local
            # image once the test finishes.
            self.addCleanup(
                client.remove_image,
                image=registry_image.full_name
            )

            name = random_name(self)
            docker_client = self.make_client()
            self.addCleanup(docker_client.remove, name)
            d = docker_client.add(name, registry_image.full_name)
            d.addCallback(
                lambda _: self.assertTrue(
                    client.inspect_image(registry_image.full_name)
                )
            )
            return d

        d = gatherResults((building, registry_listening))
        d.addCallback(create_container)
        return d

    def push_to_registry(self, image_name, registry):
        """
        Push an image identified by a local tag to the given registry.

        :param unicode image_name: The local tag which identifies the image to
            push.
        :param Registry registry: The registry to which to push the image.

        :return: A ``DockerImage`` describing the image in the registry.  Note
            in particular the tag of the image in the registry will differ from
            the local tag of the image.
        """
        registry_name = random_name(self).lower()
        registry_image = DockerImage(
            # XXX: See FLOC-246 for followup improvements to
            # ``flocker.control.DockerImage`` to allow parsing of alternative
            # registry hostnames and ports.
            repository=registry.repository + '/' + registry_name,
            tag='latest',
        )
        client = dockerpy_client()

        # Tag an image with a repository name matching the given registry.
        client.tag(
            image=image_name, repository=registry_image.repository,
            tag=registry_image.tag,
        )
        try:
            client.push(
                repository=registry_image.repository,
                tag=registry_image.tag,
            )
        finally:
            # Remove the tag created above to make it possible to do the push.
            client.remove_image(image=registry_image.full_name)

        return registry_image

    def run_registry(self):
        """
        Start a registry in a container.

        The registry will be stopped and destroyed when the currently running
        test finishes.

        :return: A ``Registry`` describing the registry which was started.
        """
        registry_name = random_name(self)
        registry_starting = self.start_container(
            unit_name=registry_name,
            image_name='registry:2',
            ports=[
                PortMap(
                    internal_port=5000,
                    # Doesn't matter what port we expose this on.  We'll
                    # discover what was assigned later.
                    external_port=0,
                ),
            ],
            retry_on_port_collision=True,
        )

        def extract_listening_port(client):
            listing = client.list()

            def listed(apps):
                [app] = [app for app in apps if app.name == registry_name]
                return next(iter(app.ports)).external_port
            listing.addCallback(listed)
            return listing

        registry_starting.addCallback(extract_listening_port)

        def wait_for_listening(external_port):
            registry = Registry(
                name=registry_name, port=external_port,
            )
            registry_listening = self.request_until_response(registry.port)
            registry_listening.addCallback(lambda ignored: registry)
            return registry_listening

        registry_starting.addCallback(wait_for_listening)

        return registry_starting

    def _pull_timeout(self):
        """
        Attempt to start an application using an image which must be pulled
        from a registry but don't give the pull operation enough time to
        complete.  Assert that the result is a timeout error of some kind.

        :return: A ``Deferred`` firing with a two-tuple of a ``DockerImage``
            and a ``Registry``.  The former represents the image we attempted
            to use, the latter represents the registry we should have tried to
            pull it from.
        """
        client = dockerpy_client()

        # Run a local registry
        running = self.run_registry()

        # Build a stub image
        def build_dummy_image(registry):
            path = FilePath(self.mktemp())
            path.makedirs()
            path.child(b"Dockerfile.in").setContent(
                b"FROM busybox\n"
                b"CMD /bin/true\n"
            )
            builder = DockerImageBuilder(
                test=self, source_dir=path,
                # We're going to manipulate the various tags on the image
                # ourselves in this test.  We'll do (the slightly more
                # complicated) cleanup so the builder shouldn't (and will
                # encounter errors if we let it).
                cleanup=False,
            )
            building = builder.build()
            building.addCallback(lambda image_name: (image_name, registry))
            return building
        running.addCallback(build_dummy_image)

        def cleanup_image(image_name):
            for image in client.images():
                if image_name in image["RepoTags"]:
                    client.remove_image(image_name, force=True)
                    return

        def cleanup_registry(registry):
            try:
                client.unpause(self.namespacing_prefix + registry.name)
            except APIError:
                # Already unpaused
                pass

        def setup_image((image_name, registry)):
            registry_image = self.push_to_registry(image_name, registry)

            # The image shouldn't be downloaded during the run of this test.
            # In case something goes wrong and it is downloaded, though, clean
            # it up.
            self.addCleanup(cleanup_image, image_name)

            # Pause the registry
            client.pause(self.namespacing_prefix + registry.name)

            # Cannot stop paused containers to make sure it gets unpaused.
            self.addCleanup(cleanup_registry, registry)

            # Create a DockerClient with a very short timeout
            docker_client = DockerClient(
                namespace=self.namespacing_prefix, long_timeout=1,
            )
            # Add an application using the DockerClient, using the tag from the
            # local registry
            app_name = random_name(self)
            d = docker_client.add(app_name, registry_image.full_name)

            # Assert that the timeout triggers.
            #
            # requests has a TimeoutError but timeout raises a ConnectionError.
            # https://github.com/kennethreitz/requests/issues/2620
            #
            # XXX DockerClient.add is our API.  We could make it fail with a
            # more coherent exception type if we wanted.
            self.assertFailure(d, ReadTimeout)
            d.addCallback(lambda ignored: (registry_image, registry))
            return d
        running.addCallback(setup_image)
        return running

    def test_pull_timeout(self):
        """
        Pulling an image times-out if it takes longer than a provided timeout.
        """
        return self._pull_timeout()

    def test_pull_timeout_pull(self):
        """
        Image pull timeout does not affect subsequent pulls.
        """
        # Note, this is the same image as test_pull_image_if_necessary, but
        # they run at different times.  Probably room for some refactoring to
        # remove the duplication between them.

        # Run all of the code from test_pull_timeout
        timing_out = self._pull_timeout()

        def pull_successfully((registry_image, registry)):
            client = dockerpy_client()
            # Resume the registry
            client.unpause(self.namespacing_prefix + registry.name)

            # Create a DockerClient with the default timeout
            docker_client = DockerClient(namespace=self.namespacing_prefix)

            # Add an application using the Client, using the tag from the local
            # registry
            app_name = random_name(self)
            adding = docker_client.add(app_name, registry_image.full_name)

            # Assert that the application runs
            return adding
        timing_out.addCallback(pull_successfully)
        return timing_out

    def test_namespacing(self):
        """
        Containers are created with a namespace prefixed to their container
        name.
        """
        docker = dockerpy_client()
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
            for _ in range(100):
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
            docker = dockerpy_client()
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
            docker = dockerpy_client()
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
            docker = dockerpy_client()
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

            d.addCallback(lambda ignored: loop_until(reactor, marker.exists))

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

    @flaky(u'FLOC-2840')
    def test_restart_policy_always(self):
        """
        An container with a restart policy of always is restarted
        after it exits.
        """
        d = self.start_restart_policy_container(
            mode=u"success-then-sleep", restart_policy=RestartAlways())

        d.addCallback(self.assertEqual, "2")
        return d

    @flaky([u'FLOC-3742', u'FLOC-3746'])
    def test_restart_policy_on_failure(self):
        """
        An container with a restart policy of on-failure is restarted
        after it exits with a non-zero result.
        """
        d = self.start_restart_policy_container(
            mode=u"failure-then-success", restart_policy=RestartOnFailure())

        d.addCallback(self.assertEqual, "2")
        return d

    @flaky([u'FLOC-3742', u'FLOC-3746'])
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


class MakeResponseTests(TestCase):
    """
    Tests for ``make_response``.
    """
    def test_str(self):
        """
        ``str(make_response(...))`` returns a string giving the response code.
        """
        self.assertEqual(
            str(make_response(123, "Something")),
            "<Response [123]>",
        )

    def test_apierror_str(self):
        """
        A string representation can be constructed of an ``APIError``
        constructed with the response returned by ``make_response``.
        """
        self.assertEqual(
            str(APIError("", make_response(500, "Simulated server error"))),
            "500 Server Error: Simulated server error",
        )


class DockerClientTests(AsyncTestCase):
    """
    Tests for ``DockerClient`` specifically.
    """
    @if_docker_configured
    def setUp(self):
        super(DockerClientTests, self).setUp()

    def test_default_namespace(self):
        """
        The default namespace is `u"flocker--"`.
        """
        docker = dockerpy_client()
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
        patcher = MonkeyPatcher()

        namespace = namespace_for_test(self)
        flocker_docker_client = DockerClient(namespace=namespace)

        name1 = random_name(self)
        adding_unit1 = flocker_docker_client.add(name1, ANY_IMAGE)
        self.addCleanup(flocker_docker_client.remove, name1)

        name2 = random_name(self)
        adding_unit2 = flocker_docker_client.add(name2, ANY_IMAGE)
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

        def get_list(ignored):
            patcher.addPatch(
                docker_client,
                'containers',
                simulate_missing_containers
            )
            patcher.patch()
            return flocker_docker_client.list()

        listing_units = adding_units.addCallback(get_list)

        def check_list(units):
            patcher.restore()
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

        response = make_response(500, "Simulated error")

        def error(name):
            raise APIError("", response)

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
        super(NamespacedDockerClientTests, self).setUp()
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
