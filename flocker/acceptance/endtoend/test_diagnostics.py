# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for the flocker-diagnostics.
"""

from subprocess import check_output
import tarfile

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

        with tarfile.open(local_archive_path) as f:
            members = [m.name for m in f.getmembers()]
            self.assertEqual([], members)
