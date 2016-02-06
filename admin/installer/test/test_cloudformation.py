# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for ``flocker.admin.installer.cloudformation``.
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
    Get fully qualified pathname of cloudformation.py script.

    :returns: Fully qualified pathname of cloudformation.py
    :rtype: twisted.python.filepath.FilePath
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
    Cluster size limits.
    """

    def setUp(self):
        """
        Gather fully qualified pathname of cloudformation.py
        """
        super(ClusterSizeLimitsTests, self).setUp()
        self._cloudformation_file = _get_cloudformation_full_path()

    def _run_cloudformation_with_cluster_size(self, cluster_size):
        """
        Create CloudFormation template for a cluster of desired size.

        :param int: Desired number of cluster nodes in the template.

        :raises: CalledProcessError
        :returns: Result of running
                  ``python cloudformation.py -s {cluster_size}``.
        :rtype: _ProcessResult
        """
        run_process_args = [b'/usr/bin/python',
                            self._cloudformation_file.path,
                            b"-s",
                            str(cluster_size)]
        result = run_process(run_process_args)
        return result

    @given(cluster_size=valid_cluster_size)
    def test_valid_cluster_size(self, cluster_size):
        """
        Create CloudFormation template for supported cluster size.
        """
        result = self._run_cloudformation_with_cluster_size(cluster_size)
        self.assertEqual(True,
                         b"node_count=\\\"%s\\\"" % (cluster_size) in
                         result.output)

    @given(cluster_size=invalid_cluster_size)
    def test_invalid_cluster_size(self, cluster_size):
        """
        Attempt to create CloudFormation template for unsupported cluster size.
        """
        output = None
        try:
            self._run_cloudformation_with_cluster_size(cluster_size)
        except CalledProcessError as e:
            output = e.output
        self.assertEquals(True,
                          'InvalidClusterSizeException' in output)
