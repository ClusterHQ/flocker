# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for the flocker-diagnostics.
"""

from subprocess import check_output
import tarfile

from twisted.python.filepath import FilePath
from twisted.trial.unittest import TestCase

from ..testtools import require_cluster


class DiagnosticsTests(TestCase):
    """
    Tests for ``flocker-diagnostics``.
    """
    @require_cluster(1)
    def test_export(self, cluster):
        """
        ``flocker-diagnostics`` creates an archive of all Flocker service logs
        and server diagnostics information.
        """
        node_address = cluster.control_node.public_address
        remote_archive_path = check_output(
            ['ssh',
             'root@{}'.format(node_address),
             'flocker-diagnostics']
        ).rstrip()

        local_archive_path = self.mktemp()

        check_output(
            ['scp',
             'root@{}:{}'.format(node_address, remote_archive_path),
             local_archive_path]
        ).rstrip()

        expected_basenames = [
            'flocker-version',
            'flocker-control',
            'flocker-dataset-agent',
            'flocker-container-agent',
            'docker-info',
            'os-release',
            'syslog',
            'uname',
            'service-status',
        ]

        with tarfile.open(local_archive_path) as f:
            self.assertEqual(
                expected_basenames,
                [FilePath(m.name).basename().splitext()
                 for m in f.getmembers()]
            )
