# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for ``flocker.testtools.cluster_utils``.
"""

from ..cluster_utils import TestTypes, make_cluster_id, MARKER
from ...testtools import TestCase


class MakeClusterIdTests(TestCase):
    """
    Tests for ``make_cluster_id``.
    """
    def test_values_extracted(self):
        """
        The values encoded by ``make_cluster_id`` into the cluster identifier
        can be extracted by ``get_cluster_id_information``.
        """
        cluster_id = make_cluster_id(TestTypes.ACCEPTANCE)
        self.assertEqual(
            (TestTypes.ACCEPTANCE.value, MARKER),
            (cluster_id.clock_seq_hi_variant, cluster_id.node),
        )
