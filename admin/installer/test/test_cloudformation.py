# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for ``flocker.admin.installer``.
"""

from os import walk
from subprocess import check_output
from sys import executable

from hypothesis import given
from hypothesis.strategies import integers

from twisted.python.filepath import FilePath

from flocker.testtools import TestCase

from .. import (
    MIN_CLUSTER_SIZE, MAX_CLUSTER_SIZE, InvalidClusterSizeException
)

# A Hypothesis strategy for generating supported cluster size.
valid_cluster_size = integers(min_value=MIN_CLUSTER_SIZE,
                              max_value=MAX_CLUSTER_SIZE)

# A Hypothesis strategy for generating unsupported cluster size.
invalid_cluster_size = integers(min_value=0,
                                max_value=MIN_CLUSTER_SIZE)


def _get_cloudformation_full_path():
    """
    """
    root_path = b'/'
    cloudformation_path_suffix = b'flocker/admin/installer'
    cloudformation_file = b'cloudformation.py'
    for root, dirs, files in walk(root_path):
        if root.endswith(cloudformation_path_suffix) \
           and cloudformation_file in files:
            return FilePath("/".join((root, cloudformation_file)))


class ClusterSizeLimitsTests(TestCase):
    """
    """

    def setUp(self):
        """
        """
        super(ClusterSizeLimitsTests, self).setUp()
        self._cloudformation_file = _get_cloudformation_full_path()

    @given(cluster_size=valid_cluster_size)
    def test_valid_cluster_size(self, cluster_size):
        """
        """
        check_output([b"python",
                      self._cloudformation_file.path,
                      b"-s",
                      str(cluster_size)])

    @given(cluster_size=invalid_cluster_size)
    def test_invalid_cluster_size(self, cluster_size):
        """
        """
        self.assertRaises(InvalidClusterSizeException,
                          executable,
                          self._cloudformation_file.path,
                          b"-s",
                          str(cluster_size))
