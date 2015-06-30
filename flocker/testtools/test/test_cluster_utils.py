# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for ``flocker.testtools._cluster_utils``.
"""

from twisted.trial.unittest import TestCase

from ..cluster_utils import (
    make_cluster_id, ClusterIdMarkers, TestTypes, Platforms, Providers
    )

INVALID_INPUT = 'invalid'


class ClusterUtilsTests(TestCase):
    """
    Tests for ``make_cluster_id``.
    """
    def test_invalid_test_type(self):
        """
        """
        test_type = INVALID_INPUT
        platform = Platforms.CENTOS7
        provider = Providers.AWS
        markers = ClusterIdMarkers()
        uuid = make_cluster_id(test_type, platform, provider)

        version = markers.version
        test_id = markers.unsupported_env
        platform_id = markers.platform_id[platform]
        provider_id = markers.provider_id[provider]
        self.assertEqual([uuid.time_hi_version, uuid.clock_seq_hi_variant,
                          uuid.clock_seq_low, uuid.node],
                         [version, test_id,
                          platform_id, provider_id])

    def test_invalid_platform(self):
        """
        """
        test_type = TestTypes.FUNCTIONAL
        platform = INVALID_INPUT
        provider = Providers.OPENSTACK
        markers = ClusterIdMarkers()

        uuid = make_cluster_id(test_type, platform, provider)
        version = markers.version
        test_id = markers.test_id[test_type]
        platform_id = markers.unsupported_env
        provider_id = markers.provider_id[provider]
        self.assertEqual([uuid.time_hi_version, uuid.clock_seq_hi_variant,
                          uuid.clock_seq_low, uuid.node],
                         [version, test_id,
                          platform_id, provider_id])

    def test_invalid_provider(self):
        """
        """
        test_type = TestTypes.ACCEPTANCE
        platform = Platforms.UBUNTU14
        provider = INVALID_INPUT
        markers = ClusterIdMarkers()

        uuid = make_cluster_id(test_type, platform, provider)
        version = markers.version
        test_id = markers.test_id[test_type]
        platform_id = markers.platform_id[platform]
        provider_id = markers.unsupported_env
        self.assertEqual([uuid.time_hi_version, uuid.clock_seq_hi_variant,
                          uuid.clock_seq_low, uuid.node],
                         [version, test_id,
                          platform_id, provider_id])

    def test_validate_cluster_id_marker(self):
        """
        """
        test_type = TestTypes.FUNCTIONAL
        platform = Platforms.UBUNTU15
        provider = Providers.AWS
        markers = ClusterIdMarkers()

        uuid = make_cluster_id(test_type, platform, provider)
        version = markers.version
        test_id = markers.test_id[test_type]
        platform_id = markers.platform_id[platform]
        provider_id = markers.provider_id[provider]
        self.assertEqual([uuid.time_hi_version, uuid.clock_seq_hi_variant,
                          uuid.clock_seq_low, uuid.node],
                         [version, test_id,
                          platform_id, provider_id])
