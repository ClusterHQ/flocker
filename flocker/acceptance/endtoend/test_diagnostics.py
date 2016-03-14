# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for ``flocker-diagnostics``.
"""

import os
import tarfile

from twisted.internet import reactor
from twisted.python.filepath import FilePath

from ...common.runner import run_ssh, download
from ...testtools import AsyncTestCase
from ..testtools import require_cluster
from testtools.matchers import MatchesAny, Equals


class DiagnosticsTests(AsyncTestCase):
    """
    Tests for ``flocker-diagnostics``.
    """
    # This only requires the container agent to check
    # that its log is collected. We still care about
    # that working, so we run it. We should stop
    # running it for this test when we get closer
    # to never running it in production.
    @require_cluster(1, require_container_agent=True)
    def test_export(self, cluster):
        """
        ``flocker-diagnostics`` creates an archive of all Flocker service logs
        and server diagnostics information.
        """
        node_address = cluster.control_node.public_address

        def create_archive():
            remote_archive_path = []
            return run_ssh(
                reactor,
                'root',
                node_address,
                ['flocker-diagnostics'],
                handle_stdout=remote_archive_path.append
            ).addCallback(
                lambda ignored: FilePath(remote_archive_path[0])
            )
        creating = create_archive()

        def download_archive(remote_archive_path):
            local_archive_path = FilePath(self.mktemp())
            return download(
                reactor=reactor,
                username=b'root',
                host=node_address.encode('ascii'),
                remote_path=remote_archive_path,
                local_path=local_archive_path,
            ).addCallback(lambda ignored: local_archive_path)
        downloading = creating.addCallback(download_archive)

        def verify_archive(local_archive_path):
            with tarfile.open(local_archive_path.path) as f:
                actual_basenames = set()
                for name in f.getnames():
                    basename = os.path.basename(name)
                    if name == basename:
                        # Ignore the directory entry
                        continue
                    actual_basenames.add(basename)

            container_agent_basenames = set([
                'flocker-container-agent_startup.gz',
                'flocker-container-agent_eliot.gz',
            ])

            expected_basenames = set([
                'flocker-control_startup.gz',
                'flocker-control_eliot.gz',
                'flocker-dataset-agent_startup.gz',
                'flocker-dataset-agent_eliot.gz',
                'flocker-docker-plugin_startup.gz',
                'flocker-docker-plugin_eliot.gz',
                'flocker-version',
                'docker-info',
                'docker-version',
                'os-release',
                'syslog.gz',
                'uname',
                'service-status',
                'ip-addr',
                'hostname',
                'lsblk',
                'fdisk',
                'lshw',
            ])
            self.expectThat(
                actual_basenames,
                MatchesAny([
                    Equals(expected_basenames),
                    Equals(expected_basenames.union(container_agent_basenames)),
                ])
            )

        verifying = downloading.addCallback(verify_archive)

        return verifying
