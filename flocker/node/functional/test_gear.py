# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""Functional tests for :module:`flocker.node.gear`."""

import os
from unittest import skipIf

from ..test.test_gear import make_igearclient_tests
from ..gear import GearClient

# Allow setting gear server location:
GEAR_HOST = os.getenv("GEAR_HOST", None)
_if_gear_configured = skipIf(
    GEAR_HOST is None,
    "Must set GEAR_HOST env variable to run functional gear tests.")


class IGearClientTests(make_igearclient_tests(
        lambda test_case: GearClient(GEAR_HOST))):
    """``IGearClient`` tests for ``FakeGearClient``."""

    @_if_gear_configured
    def setUp(self):
        pass


# XXX still needs tests to ensure container is actually started.
# XXX still need to write documentation.
# XXX need test to ensure correct image was used... perhaps with Dockerfile?
