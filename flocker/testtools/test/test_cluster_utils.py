# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for ``flocker.testtools._cluster_utils``.
"""

from twisted.trial.unittest import TestCase

from ..cluster_utils import (
    make_cluster_id, ClusterIdMarkers, TestTypes, Providers
    )

INVALID_INPUT = 'invalid'


class ClusterUtilsTests(TestCase):
    """
    Tests for ``make_cluster_id``.
    """
    def test_invalid_test_type(self):
        """
        Test if invalid test type is registered in cluster uuid.
        """
        test_type = INVALID_INPUT
        provider = 'openstack'
        markers = ClusterIdMarkers()
        uuid = make_cluster_id(test_type, provider)

        version = markers.version
        test_id = markers.unsupported_env
        provider_id = markers.provider_id[Providers.lookupByValue(provider)]
        self.assertEqual([uuid.clock_seq_hi_variant, uuid.clock_seq_low,
                          uuid.node],
                         [version, test_id, provider_id])

    def test_invalid_provider(self):
        """
        Test if invalid provider type is registered in cluster uuid.
        """
        test_type = TestTypes.ACCEPTANCE
        provider = INVALID_INPUT
        markers = ClusterIdMarkers()

        uuid = make_cluster_id(test_type, provider)
        version = markers.version
        test_id = markers.test_id[test_type]
        provider_id = markers.unsupported_env
        self.assertEqual([uuid.clock_seq_hi_variant, uuid.clock_seq_low,
                          uuid.node],
                         [version, test_id, provider_id])

    def test_validate_cluster_id_marker(self):
        """
        Test if valid test env results in valid markers in generated uuid.
        """
        test_type = TestTypes.FUNCTIONAL
        provider = 'aws'
        markers = ClusterIdMarkers()

        uuid = make_cluster_id(test_type, provider)
        version = markers.version
        test_id = markers.test_id[test_type]
        provider_id = 1
        self.assertEqual([uuid.clock_seq_hi_variant, uuid.clock_seq_low,
                          uuid.node],
                         [version, test_id, provider_id])
