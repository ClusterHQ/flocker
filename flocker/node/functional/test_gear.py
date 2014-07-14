# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""Functional tests for :module:`flocker.node.gear`."""

import os
import json
import subprocess
import socket
from unittest import skipIf

from twisted.trial.unittest import TestCase
from twisted.python.procutils import which
from twisted.python.filepath import FilePath
from twisted.internet.defer import succeed
from twisted.internet.error import ConnectionRefusedError
from twisted.internet.endpoints import TCP4ServerEndpoint
from twisted.internet import reactor

from treq import request, content

from ...testtools import (
    loop_until, find_free_port, make_capture_protocol,
    ProtocolPoppingFactory, DockerImageBuilder)

from ..test.test_gear import make_igearclient_tests, random_name
from ..gear import GearClient, GearError, GEAR_PORT, Unit, PortMap


def _gear_running():
    """Return whether gear is running on this machine.

    :return: ``True`` if gear can be reached, otherwise ``False``.
    """
    if not which("gear"):
        return False
    sock = socket.socket()
    try:
        return not sock.connect_ex((b'127.0.0.1', GEAR_PORT))
    finally:
        sock.close()
_if_gear_configured = skipIf(not _gear_running(),
                             "Must run on machine with `gear daemon` running.")
_if_root = skipIf(os.getuid() != 0, "Must run as root.")


class IGearClientTests(make_igearclient_tests(
        lambda test_case: GearClient("127.0.0.1"))):
    """``IGearClient`` tests for ``FakeGearClient``."""

    @_if_gear_configured
    def setUp(self):
        pass


class GearClientTests(TestCase):
    """Implementation-specific tests for ``GearClient``."""

    @_if_gear_configured
    def setUp(self):
        pass

    def start_container(self, unit_name,
                        image_name=u"openshift/busybox-http-app",
                        ports=None, links=None, expected_state=None):
        """
        Start a unit and wait until it reaches the `active` state or the
        supplied `expected_state`.

        :param unicode unit_name: See ``IGearClient.add``.
        :param unicode image_name: See ``IGearClient.add``.
        :param list ports: See ``IGearClient.add``.
        :param list links: See ``IGearClient.add``.
        :param Unit expected_state: A ``Unit`` representing target state at
            which the newly started unit will be considered started. By default
            this is a ``Unit`` with the supplied name and an `activation_state`
            of `active` but this can be overridden in tests for units which are
            expected to fail.

        :return: ``Deferred`` that fires with the ``GearClient`` when the unit
            reaches the expected state.
        """
        if expected_state is None:
            expected_state = Unit(name=unit_name, activation_state=u"active",
                                  sub_state=u"running")
        client = GearClient("127.0.0.1")
        d = client.add(
            unit_name=unit_name,
            image_name=image_name,
            ports=ports,
            links=links,
        )
        self.addCleanup(client.remove, unit_name)

        def is_started(units):
            return expected_state in units

        def check_if_started():
            responded = client.list()
            responded.addCallback(is_started)
            return responded

        def added(_):
            return loop_until(check_if_started)
        d.addCallback(added)
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
        client = GearClient("127.0.0.1")
        # add() calls exists(), and we don't want exists() to be the one
        # failing since that's not the code path we're testing, so bypass
        # it:
        client.exists = lambda _: succeed(False)
        # Illegal container name should make gear complain when we try to
        # install the container:
        d = client.add(u"!!!###!!!", u"busybox")
        return self.assertFailure(d, GearError)

    def test_remove_error(self):
        """``GearClient.remove`` returns ``Deferred`` that errbacks with
        ``GearError`` if response code is not a success response code.
        """
        client = GearClient("127.0.0.1")
        # Illegal container name should make gear complain when we try to
        # remove it:
        d = client.remove(u"!!##!!")
        return self.assertFailure(d, GearError)

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
            def is_stopped(units):
                return [unit for unit in units if
                        (unit.name == name and
                         unit.activation_state in
                         (u"inactive", u"deactivating", u"failed"))]

            def check_if_stopped():
                responded = client.list()
                responded.addCallback(is_stopped)
                return responded

            return loop_until(check_if_stopped)

        d.addCallback(stopped)
        return d

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
        expected_state = Unit(name=name, activation_state=u'inactive',
                              sub_state=u'dead')
        d = self.start_container(unit_name=name, image_name="busybox",
                                 expected_state=expected_state)
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

    def test_add_with_links(self):
        """
        ``GearClient.add`` accepts a links argument which sets up links between
        container local ports and host local ports.
        """
        internal_port = 31337
        expected_bytes = b'foo bar baz'
        image_name = b'flocker/send_bytes_to'
        # Create a Docker image
        image = DockerImageBuilder(
            source_dir=FilePath(__file__).sibling('docker'),
            tag=image_name,
            working_dir=FilePath(self.mktemp())
        )
        image.build(
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
