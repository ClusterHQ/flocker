# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for ``flocker.testtools._cluster_utils``.
"""

from twisted.trial.unittest import TestCase

from ..cluster_utils import make_cluster_id


class ClusterUtilsTests(TestCase):
    """
    Tests for ``make_cluster_id``.
    """
    def test_invalid_test_type(self):
        """
        """
        test_type = 'invalid-type'
        platform = 'centos-7'
        provider = 'aws'
        self.assertRaises(Exception, make_cluster_id, test_type, platform,
                          provider)

    def test_invalid_platform(self):
        """
        """
        test_type = 'functional'
        platform = 'invalid-platform'
        provider = 'aws'
        self.assertRaises(Exception, make_cluster_id, test_type, platform,
                          provider)

    def test_invalid_provider(self):
        """
        """
        test_type = 'acceptance'
        platform = 'centos-7'
        provider = 'openstack'
        self.assertRaises(Exception, make_cluster_id, test_type, platform,
                          provider)

    def validate_cluster_id_marker(self):
        """
        """
        test_type = 'acceptance'
        platform = 'ubuntu-14.04'
        provider = 'openstack'
        self.assertEqual(make_cluster_id(test_type, platform, provider), 111)
