# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for the flocker-diagnostics.
"""

import os
from subprocess import check_output
import tarfile

from twisted.trial.unittest import TestCase

from ..testtools import require_cluster

# XXX: Copied from ``flocker.admin.acceptance``.
# Should probably refactor and re-use ``flocker.admin.runner`` too.
SSH_OPTIONS = [
    b"-q",  # suppress warnings
    # We're ok with unknown hosts.
    b"-o", b"StrictHostKeyChecking=no",
    # The tests hang if ControlMaster is set, since OpenSSH won't
    # ever close the connection to the test server.
    b"-o", b"ControlMaster=no",
    # Some systems (notably Ubuntu) enable GSSAPI authentication which
    # involves a slow DNS operation before failing and moving on to a
    # working mechanism.  The expectation is that key-based auth will
    # be in use so just jump straight to that.
    b"-o", b"PreferredAuthentications=publickey",
]


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
            ['ssh'] + SSH_OPTIONS +
            ['root@{}'.format(node_address),
             'flocker-diagnostics']
        ).rstrip()

        local_archive_path = self.mktemp()

        check_output(
            ['scp'] + SSH_OPTIONS +
            ['root@{}:{}'.format(node_address, remote_archive_path),
             local_archive_path]
        ).rstrip()

        with tarfile.open(local_archive_path) as f:
            actual_basenames = []
            for name in f.getnames():
                basename = os.path.basename(name)
                if name == basename:
                    # Ignore the directory entry
                    continue
                actual_basenames.append(basename)

        expected_basenames = [
            'flocker-control_startup.gz',
            'flocker-control_eliot.gz',
            'flocker-dataset-agent_startup.gz',
            'flocker-dataset-agent_eliot.gz',
            'flocker-container-agent_startup.gz',
            'flocker-container-agent_eliot.gz',
            'flocker-version',
            'docker-info',
            'docker-version',
            'os-release',
            'syslog.gz',
            'uname',
            'service-status',
            'ip-addr',
            'hostname',
        ]

        missing_basenames = set(expected_basenames) - set(actual_basenames)
        unexpected_basenames = set(actual_basenames) - set(expected_basenames)

        message = []
        if unexpected_basenames:
            message.append(
                'Unexpected entries: {!r}'.format(unexpected_basenames)
            )

        if missing_basenames:
            message.append('Missing entries: {!r}'.format(missing_basenames))

        if message:
            self.fail(
                'Unexpected Archive Content\n'
                + '\n'.join(message)
            )
