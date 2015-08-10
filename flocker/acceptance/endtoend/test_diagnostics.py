# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for the flocker-diagnostics.
"""

from twisted.trial.unittest import TestCase

from ...testtools import loop_until

from ..testtools import (
    require_cluster, require_moving_backend, create_dataset,
    REALISTIC_BLOCKDEVICE_SIZE,
)


class DatasetAPITests(TestCase):
    """
    Tests for the dataset API.
    """
    @require_cluster(1)
    def test_export(self, cluster):
        """
        A dataset can be created on a specific node.
        """
        import pdb; pdb.set_trace()
        self.fail('not implemented')
