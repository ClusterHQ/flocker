# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""Functional tests for :module:`flocker.node.gear`."""

import os
import json
import subprocess
from unittest import skipIf

from twisted.trial.unittest import TestCase
from twisted.python.filepath import FilePath
from twisted.internet.defer import succeed
from twisted.internet.error import ConnectionRefusedError
from twisted.internet.endpoints import TCP4ServerEndpoint
from twisted.internet import reactor
from twisted.internet.utils import getProcessOutput

from treq import request, content

from ...testtools import (
    loop_until, find_free_port, make_capture_protocol,
    ProtocolPoppingFactory, DockerImageBuilder, assertContainsAll)

from ..test.test_gear import make_igearclient_tests, random_name
from ..gear import GearClient, GearError, PortMap, GearEnvironment
from ..testtools import if_gear_configured, wait_for_unit_state

_if_root = skipIf(os.getuid() != 0, "Must run as root.")


class IGearClientTests(make_igearclient_tests(
        lambda test_case: GearClient("127.0.0.1"))):
    """``IGearClient`` tests for ``GearClient``."""

    @if_gear_configured
    def setUp(self):
        pass


class GearClientTestsMixin(object):
    """
    Implementation-specific tests mixin for ``GearClient`` and similar
    classes (in particular, ``DockerClient``).
    """
    # Override with Exception subclass used by the client
    clientException = None

    def make_client(self):
        """
        Create a client.

        :return: A ``IGearClient`` provider.
        """
        raise NotImplementedError("Implement in subclasses")

    def start_container(self, unit_name,
                        image_name=u"openshift/busybox-http-app",
                        ports=None, links=None, expected_states=(u'active',),
                        environment=None):
        """
        Start a unit and wait until it reaches the `active` state or the
        supplied `expected_state`.

        :param unicode unit_name: See ``IGearClient.add``.
        :param unicode image_name: See ``IGearClient.add``.
        :param list ports: See ``IGearClient.add``.
        :param list links: See ``IGearClient.add``.
        :param Unit expected_states: A list of activation states to wait for.

        :return: ``Deferred`` that fires with the ``GearClient`` when the unit
            reaches the expected state.
        """
        client = self.make_client()
        d = client.add(
            unit_name=unit_name,
            image_name=image_name,
            ports=ports,
            links=links,
            environment=environment,
        )
        self.addCleanup(client.remove, unit_name)

        d.addCallback(lambda _: wait_for_unit_state(client, unit_name,
                                                    expected_states))
        d.addCallback(lambda _: client)

        return d

    def test_add_starts_container(self):
        """``GearClient.add`` starts the container."""
        name = random_name()
        return self.start_container(name)

    @_if_root
    def test_correct_image_used(self):
        """``GearClient.add`` creates a container with the specified image."""
        name = random_name()
        d = self.start_container(name)

        def started(_):
            data = subprocess.check_output(
                [b"docker", b"inspect", name.encode("ascii")])
            self.assertEqual(json.loads(data)[0][u"Config"][u"Image"],
                             u"openshift/busybox-http-app")
        d.addCallback(started)
        return d

    def test_add_error(self):
        """``GearClient.add`` returns ``Deferred`` that errbacks with
        ``GearError`` if response code is not a success response code.
        """
        client = self.make_client()
        # add() calls exists(), and we don't want exists() to be the one
        # failing since that's not the code path we're testing, so bypass
        # it:
        client.exists = lambda _: succeed(False)
        # Illegal container name should make gear complain when we try to
        # install the container:
        d = client.add(u"!!!###!!!", u"busybox")
        return self.assertFailure(d, self.clientException)

    def test_remove_error(self):
        """``GearClient.remove`` returns ``Deferred`` that errbacks with
        ``GearError`` if response code is not a success response code.
        """
        client = self.make_client()
        # Illegal container name should make gear complain when we try to
        # remove it:
        d = client.remove(u"!!##!!")
        return self.assertFailure(d, self.clientException)

    def test_dead_is_listed(self):
        """
        ``GearClient.list()`` includes dead units.

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
                Catch ConnectionRefused errors and return False so that
                loop_until repeats the request.

                Other error conditions will be passed down the errback chain.
                """
                failure.trap(ConnectionRefusedError)
                return False
            response.addErrback(check_error)
            return response

        return loop_until(send_request)

    def test_add_with_port(self):
        """
        GearClient.add accepts a ports argument which is passed to gear to
        expose those ports on the unit.

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

    def test_slow_removed_unit_does_not_exist(self):
        """
        ``remove()`` only fires once the Docker container has shut down.
        """
        client = GearClient(b"127.0.0.1")
        name = random_name()
        image = self.build_slow_shutdown_image()
        d = self.start_container(name, image)
        d.addCallback(lambda _: client.remove(name))

        def removed(_):
            process = subprocess.Popen(
                [b"docker", b"inspect", name.encode("ascii")])
            # Inspect gives non-zero exit code for stopped and
            # non-existent containers:
            self.assertEqual(process.wait(), 1)
        d.addCallback(removed)
        return d

    @_if_root
    def test_add_with_environment(self):
        """
        ``GearClient.add`` accepts an environment object whose ID and variables
        are used when starting a docker image.
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
        expected_environment_id = random_name()
        expected_variables = frozenset({
            'key1': 'value1',
            'key2': 'value2',
        }.items())
        d = self.start_container(
            unit_name=unit_name,
            image_name=image_name,
            environment=GearEnvironment(
                id=expected_environment_id, variables=expected_variables),
        )
        d.addCallback(
            lambda ignored: getProcessOutput(b'docker', [b'logs', unit_name],
                                             env=os.environ,
                                             # Capturing stderr makes
                                             # debugging easier:
                                             errortoo=True)
        )
        d.addCallback(
            assertContainsAll,
            test_case=self,
            needles=['{}={}\n'.format(k, v) for k, v in expected_variables],
        )
        return d


class GearClientTests(TestCase, GearClientTestsMixin):
    """Implementation-specific tests for ``GearClient``."""

    @if_gear_configured
    def setUp(self):
        pass

    clientException = GearClient

    def make_client(self):
        return GearClient("127.0.0.1")

    def test_stopped_is_listed(self):
        """
        ``GearClient.list()`` includes stopped units.

        In certain old versions of geard the API was such that you had to
        explicitly request stopped units to be listed, so we want to make
        sure this keeps working.
        """
        name = random_name()
        d = self.start_container(name)

        def started(client):
            self.addCleanup(client.remove, name)

            # Stop the unit, an operation that is not exposed directly by
            # our current API:
            stopped = client._container_request(
                b"PUT", name, operation=b"stopped")
            stopped.addCallback(client._ensure_ok)
            stopped.addCallback(lambda _: client)
            return stopped
        d.addCallback(started)

        def stopped(client):
            return wait_for_unit_state(
                client, name, (u"inactive", u"deactivating", u"failed"))
        d.addCallback(stopped)
        return d

    def test_add_with_links(self):
        """
        ``GearClient.add`` accepts a links argument which sets up links between
        container local ports and host local ports.
        """
        internal_port = 31337
        expected_bytes = b'foo bar baz'
        # Create a Docker image
        image = DockerImageBuilder(
            test=self,
            source_dir=FilePath(__file__).sibling('sendbytes-docker'),
        )
        image_name = image.build(
            dockerfile_variables=dict(
                host=b'127.0.0.1',
                port=internal_port,
                bytes=expected_bytes,
                timeout=30
            )
        )

        # This is the target of the proxy which will be created.
        server = TCP4ServerEndpoint(reactor, 0)
        capture_finished, protocol = make_capture_protocol()

        def check_data(data):
            self.assertEqual(expected_bytes, data)
        capture_finished.addCallback(check_data)

        factory = ProtocolPoppingFactory(protocols=[protocol])
        d = server.listen(factory)

        def start_container(port):
            self.addCleanup(port.stopListening)
            host_port = port.getHost().port
            return self.start_container(
                unit_name=random_name(),
                image_name=image_name,
                links=[PortMap(internal_port=internal_port,
                               external_port=host_port)]
            )
        d.addCallback(start_container)

        def started(ignored):
            return capture_finished
        d.addCallback(started)

        return d
