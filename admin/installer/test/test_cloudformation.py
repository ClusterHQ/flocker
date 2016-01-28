# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for ``flocker.admin.installer``.
"""

from subprocess import check_output

from hypothesis import given
from hypothesis.strategies import integers

from twisted.python.filepath import FilePath

from flocker.testtools import TestCase

from .. import MIN_CLUSTER_SIZE, MAX_CLUSTER_SIZE

# A Hypothesis strategy for generating supported cluster size.
valid_cluster_size = integers(min_value=MIN_CLUSTER_SIZE,
                              max_value=MAX_CLUSTER_SIZE)


class ClusterSizeLimitsTests(TestCase):
    """
    """
    @given(cluster_size=integers(min_value=MIN_CLUSTER_SIZE,
           max_value=MAX_CLUSTER_SIZE))
    def test_valid_cluster(self, cluster_size):
        """
        """
        cloudformation_file = FilePath(b"cloudformation.py").realpath()
        check_output([b"python",
                      cloudformation_file.path,
                      b"-s",
                      str(cluster_size)])
