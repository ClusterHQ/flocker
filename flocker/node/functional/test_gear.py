# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""Functional tests for :module:`flocker.node.gear`."""

import os
import json
from unittest import skipIf

from twisted.trial.unittest import TestCase

from treq import request, content

from ...testtools import loop_until
from ..test.test_gear import make_igearclient_tests, random_name
from ..gear import GearClient


# Allow setting gear server location:
GEAR_HOST = os.getenv("GEAR_HOST", None)


_if_gear_configured = skipIf(
    GEAR_HOST is None,
    "Must set GEAR_HOST env variable to run functional gear tests.")
_if_root = skipIf(os.getuid() != 0, "Must run as root.")


class IGearClientTests(make_igearclient_tests(
        lambda test_case: GearClient(GEAR_HOST))):
    """``IGearClient`` tests for ``FakeGearClient``."""

    @_if_gear_configured
    def setUp(self):
        pass


class GearClientTests(TestCase):
    """Implementation-specific tests for ``GearClient``."""

    @_if_gear_configured
    def setUp(self):
        pass

    def test_add_starts_container(self):
        """``GearClient.add`` starts the container."""
        client = GearClient(GEAR_HOST)
        name = random_name()
        d = client.add(name, u"openshift/busybox-http-app")

        def is_started(data):
            return [container for container in data[u"Containers"] if
                    (container[u"Id"] == name and
                     container[u"SubState"] == u"running")]

        def check_if_started():
            # Replace with ``GearClient.list`` as part of
            # https://github.com/hybridlogic/flocker/issues/32
            responded = request(
                b"GET", b"http://%s:43273/containers" % (GEAR_HOST,),
                persistent=False)
            responded.addCallback(content)
            responded.addCallback(json.loads)
            responded.addCallback(is_started)
            return responded

        def added(_):
            self.addCleanup(client.remove, name)
            return loop_until(None, check_if_started)
        d.addCallback(added)
        return d

    @_if_root
    def test_correct_image_used(self):
        """``GearClient.add`` creates a container with the specified image."""

    def test_exists_error(self):
        """``GearClient.exists`` returns ``Deferred`` that errbacks with
        ``GearError`` if response code is unexpected.
        """

    def test_add_error(self):
        """``GearClient.add`` returns ``Deferred`` that errbacks with
        ``GearError`` if response code is unexpected.
        """

    def test_remove_error(self):
        """``GearClient.remove`` returns ``Deferred`` that errbacks with
        ``GearError`` if response code is unexpected.
        """


# XXX still need to write documentation.

