# Copyright ClusterHQ Inc. See LICENSE file for details.

"""
Tests for common provision code.
"""

from flocker.common.version import make_rpm_version
from flocker.provision._common import PackageSource
from flocker.testtools import TestCase


class PackageSourceTests(TestCase):
    """
    Tests for ``PackageSource.os_version``.
    """
    def test_os_version(self):
        """
        os_version() returns an OS version for a FLocker version.
        """
        version = '1.2.3'
        rpm_version = make_rpm_version(version)
        expected = "%s-%s" % (rpm_version.version, rpm_version.release)
        package_source = PackageSource(version=version)
        self.assertEqual(expected, package_source.os_version())

    def test_version_none(self):
        """
        Unset version gives no OS version.
        """
        package_source = PackageSource()
        self.assertFalse(package_source.os_version())

    def test_version_empty(self):
        """
        Empty version gives no OS version.  This is supported, due to
        a previously undocumented behavior being useful.
        """
        package_source = PackageSource(version='')
        self.assertFalse(package_source.os_version())
