# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""Functional tests for :module:`flocker.node.gear`."""

import os
from unittest import skipIf

from twisted.trial.unittest import TestCase

from ..test.test_gear import make_igearclient_tests
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

    @_if_root
    def test_add_starts_container(self):
        """``GearClient.add`` starts the container."""

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


# XXX don't rely on ability to install busybox from the network

# XXX still need to write documentation.

