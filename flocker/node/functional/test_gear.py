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

from treq import request, content

from ...testtools import loop_until
from ..test.test_gear import make_igearclient_tests, random_name
from ..gear import GearClient, GearError, GEAR_PORT


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

    def start_container(self, name):
        """Start a unit and wait until it's up and running.

        :param unicode name: The name of the unit.

        :return: Deferred that fires when the unit is running.
        """
        client = GearClient("127.0.0.1")
        d = client.add(name, u"openshift/busybox-http-app")
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
