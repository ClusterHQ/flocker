# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for ``flocker.admin.installer``.
"""

from os import walk
from subprocess import CalledProcessError

from hypothesis import given
from hypothesis.strategies import integers, one_of

from twisted.python.filepath import FilePath

from flocker.testtools import TestCase, run_process

from .. import MIN_CLUSTER_SIZE, MAX_CLUSTER_SIZE

# A Hypothesis strategy for generating supported cluster size.
valid_cluster_size = integers(min_value=MIN_CLUSTER_SIZE,
                              max_value=MAX_CLUSTER_SIZE)

# A Hypothesis strategy for generating unsupported cluster size.
too_small_cluster_size = integers(min_value=0,
                                  max_value=MIN_CLUSTER_SIZE-1)
too_big_cluster_size = integers(min_value=MAX_CLUSTER_SIZE+1,
                                max_value=100)
invalid_cluster_size = one_of(too_small_cluster_size, too_big_cluster_size)


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

    def _run_cloudformation_with_cluster_size(self, size):
        """
        """
        run_process_args = [b'/usr/bin/python',
                            self._cloudformation_file.path,
                            b"-s",
                            str(size)]
        run_process(run_process_args)

    @given(cluster_size=valid_cluster_size)
    def test_valid_cluster_size(self, cluster_size):
        """
        """
        self._run_cloudformation_with_cluster_size(cluster_size)

    @given(cluster_size=invalid_cluster_size)
    def test_invalid_cluster_size(self, cluster_size):
        """
        """
        output = None
        try:
            self._run_cloudformation_with_cluster_size(cluster_size)
        except CalledProcessError as e:
            output = e.output
        self.assertEquals(True,
                          'InvalidClusterSizeException' in output)
