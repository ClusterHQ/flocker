# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for the flocker-diagnostics.
"""

import os
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
            actual_basenames = [
                os.path.basename(os.path.splitext(m.name)[0])
                for m in f.getmembers()
            ]

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

        missing_basenames = set(expected_basenames) - set(actual_basenames)
        unexpected_basenames = set(actual_basenames) - set(expected_basenames)

        if unexpected_basenames:
            # with tarfile.open(local_archive_path) as f:
            self.fail('Unexpected entries: {!r}'.format(unexpected_basenames))

        if missing_basenames:
            # with tarfile.open(local_archive_path) as f:
            self.fail('Missing entries: {!r}'.format(missing_basenames))
