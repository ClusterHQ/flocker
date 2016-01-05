# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for ``flocker.common._era``.
"""

from uuid import UUID
from unittest import skipUnless

from twisted.python.runtime import platform
from .._era import get_era
from ...testtools import TestCase


class EraTests(TestCase):
    """
    Tests for ``get_era``
    """
    @skipUnless(platform.isLinux(), "get_era() only supported on Linux.")
    def setUp(self):
        super(EraTests, self).setUp()

    def test_get_era(self):
        """
        The era is the current unique ``boot_id``.

        This rather duplicates the implementation, but can't do much
        better.
        """
        with open("/proc/sys/kernel/random/boot_id") as f:
            self.assertEqual(get_era(),
                             UUID(hex=f.read().strip()))

    def test_repeated(self):
        """
        Repeated calls give the same result.
        """
        values = set(get_era() for i in range(100))
        self.assertEqual(len(values), 1)
