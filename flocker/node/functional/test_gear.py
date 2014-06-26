# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""Functional tests for :module:`flocker.node.gear`."""

import os
import json
import subprocess
import socket
from unittest import skipIf

from twisted.trial.unittest import TestCase
from twisted.python.procutils import which
from twisted.internet.defer import succeed
from twisted.internet.test.connectionmixins import findFreePort

from treq import request, content

from characteristic import attributes

from ...testtools import loop_until, loop_until2
from ..test.test_gear import make_igearclient_tests, random_name
from ..gear import GearClient, GearError, GEAR_PORT, PortMap


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

    def start_container(self, name, image_name=u"openshift/busybox-http-app", ports=None, links=None):
        """Start a unit and wait until it's up and running.

        :param unicode name: The name of the unit.
        :param list links: A list of ``PortMap`` instances describing the
            network links between the container and the host.

        :return: Deferred that fires when the unit is running.
        """
        client = GearClient("127.0.0.1")
        d = client.add(name, image_name, ports=ports, links=links)
        self.addCleanup(client.remove, name)

        def is_started(data):
            return [container for container in data[u"Containers"] if
                    (container[u"Id"] == name and
                     container[u"SubState"] == u"running")]

        def check_if_started():
            # Replace with ``GearClient.list`` as part of
            # https://github.com/hybridlogic/flocker/issues/32
            responded = request(
                b"GET", b"http://127.0.0.1:%d/containers" % (GEAR_PORT,),
                persistent=False)
            responded.addCallback(content)
            responded.addCallback(json.loads)
            responded.addCallback(is_started)
            return responded

        def added(_):
            return loop_until(None, check_if_started)
        d.addCallback(added)
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

    def test_exists_error(self):
        """``GearClient.exists`` returns ``Deferred`` that errbacks with
        ``GearError`` if response code is unexpected.
        """
        client = GearClient("127.0.0.1")
        # Illegal container name should make gear complain when we check
        # if it exists:
        d = client.exists(u"!!##!!")
        return self.assertFailure(d, GearError)

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

    def assert_busybox_http_response(self, response):
        """
        Assert that the busybox-http-app returns the expected "Hello world!"
        response.

        XXX: We should use a stable internal container instead. See
        https://github.com/hybridlogic/flocker/issues/120

        XXX: The busybox-http-app returns headers in the body of its response,
        hence this over complicated custom assertion. See
        https://github.com/openshift/geard/issues/213
        """
        expected_response = b'Hello world!\n'
        actual_response = response[-len(expected_response):]
        message = (
            "Response {response} does not end with {expected_response}. "
            "Found {actual_response}.".format(
                response=repr(response),
                expected_response=repr(expected_response),
                actual_response=repr(actual_response)
            )
        )
        self.assertEqual(
            expected_response,
            actual_response,
            message
        )


    def request_until_response(self, port):
        """
        """
        def send_request():
            response = request(
                b"GET", b"http://127.0.0.1:%d" % (port,),
                persistent=False)
            # Catch errors and return False so that loop_until repeats the
            # request.
            # XXX: This will hide all errors. We should probably only catch
            # timeouts and reject responses here.
            response.addErrback(lambda err: False)
            return response

        # The container may have started, but the webserver inside may take a
        # little while to start serving requests. Resend our test request
        # until we get a response.
        return loop_until2(send_request)

    def test_add_with_port(self):
        """
        GearClient.add accepts a ports argument which is passed to gear to
        expose those ports on the unit.
        """
        external_port = findFreePort()[1]
        name = random_name()
        d = self.start_container(
            name, ports=[PortMap(internal=8080, external=external_port)])

        d.addCallback(lambda ignored: self.request_until_response(external_port))

        def started(response):
            d = content(response)
            d.addCallback(self.assert_busybox_http_response)
            return d
        d.addCallback(started)

        return d

    def test_add_error_unless_internal_exposed(self):
        """
        Raises error when the chosen internal port has not been exposed by the
        container.
        """
        self.fail()

    def test_add_error_if_external_port_in_use(self):
        """
        Raises error if the chosen external port is already exposed.
        """
        self.fail()


    def test_add_with_links(self):
        """
        GearClient.add accepts a links argument which sets up links between
        container local ports and host local ports.
        """
        internal_port = 31337
        image_name = b'flocker/send_xxx_to_31337'
        # Create a Docker image
        image = DockerImageBuilder(
            docker_dir=os.path.dirname(__file__),
            tag=image_name
        )
        image.build()
        self.addCleanup(image.remove)

        # This is the target of the proxy which will be created.
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setblocking(0)
        server.bind((b'127.0.0.1', 0))
        server.listen(1)
        host_port = server.getsockname()[1]
        name = random_name()
        d = self.start_container(
            name, image_name=image_name, links=[PortMap(internal=internal_port, external=host_port)])

        def started(ignored):
            accepted, client_address = server.accept()
            self.assertEqual(b'XXX', accepted.read())
        d.addCallback(started)

        return d


@attributes(['docker_dir', 'tag'])
class DockerImageBuilder(object):
    def build(self):
        command = [
            b'docker', b'build',
            b'--force-rm',
            b'--tag=%s' % (self.tag,),
            self.docker_dir
        ]
        subprocess.check_call(command)

    def remove(self):
        command = [
            b'docker', b'rmi',
            b'--force',
            self.tag
        ]
        subprocess.check_call(command)
