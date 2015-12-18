# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Functional tests for ``flocker-node-era`` command.
"""

from unittest import skipUnless
from subprocess import check_output

from twisted.python.procutils import which
from twisted.python.runtime import platform

from .._era import get_era
from ...testtools import make_script_tests

EXECUTABLE = b"flocker-node-era"


class FlockerNodeEraTests(make_script_tests(EXECUTABLE)):
    """
    Tests for ``flocker-node-era``.
    """
    @skipUnless(which(EXECUTABLE), EXECUTABLE + " not installed")
    @skipUnless(platform.isLinux(), "flocker-node-era only works on Linux")
    def setUp(self):
        super(FlockerNodeEraTests, self).setUp()

    def test_output(self):
        """
        The process outputs the same information as ``get_era()``.
        """
        self.assertEqual(check_output(EXECUTABLE),
                         str(get_era()))

    def test_repeatable_output(self):
        """
        The process outputs the same information when called multiple times,
        since it shoudl only change on reboot.
        """
        self.assertEqual(check_output(EXECUTABLE),
                         check_output(EXECUTABLE))
