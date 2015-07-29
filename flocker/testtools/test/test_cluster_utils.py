# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for ``flocker.testtools.cluster_utils``.
"""

from uuid import UUID

from twisted.trial.unittest import SynchronousTestCase

from ..cluster_utils import (
    VERSION, get_version, make_cluster_id, get_cluster_id_information,
    TestTypes, Providers,
)


class GetVersionTests(SynchronousTestCase):
    """
    Tests for ``get_version``.
    """
    def test_same_results(self):
        """
        Given the same arguments, multiple calls to ``get_version`` return the
        same value.
        """
        self.assertEqual(
            get_version(TestTypes, Providers),
            get_version(TestTypes, Providers),
        )

    def test_different_results(self):
        """
        Given different arguments, multiple calls to ``get_version`` return
        different values.
        """
        self.assertNotEqual(
            get_version(TestTypes, Providers),
            get_version(Providers, TestTypes),
        )


class ClusterIdTests(SynchronousTestCase):
    """
    Tests for ``make_cluster_id`` and ``get_cluster_id_information``.
    """
    def test_foreign_id(self):
        """
        ``get_cluster_id_information`` raises ``ValueError`` if called with a
        cluster identifier that didn't come from ``make_cluster_id``.
        """
        self.assertRaises(
            ValueError,
            get_cluster_id_information,
            UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"),
        )

    def test_version_mismatch(self):
        """
        ``get_cluster_id_information`` raises ``ValueError`` if called with a
        cluster identifier that came from ``make_cluster_id`` from an
        incompatible version of Flocker.
        """
        cluster_id = make_cluster_id(
            TestTypes.ACCEPTANCE, Providers.AWS, VERSION + 1
        )
        self.assertRaises(
            ValueError,
            get_cluster_id_information,
            cluster_id,
        )

    def test_values_extracted(self):
        """
        The values encoded by ``make_cluster_id`` into the cluster identifier
        can be extracted by ``get_cluster_id_information``.
        """
        cluster_id = make_cluster_id(TestTypes.ACCEPTANCE, Providers.AWS)
        self.assertEqual(
            (TestTypes.ACCEPTANCE, Providers.AWS),
            get_cluster_id_information(cluster_id),
        )
