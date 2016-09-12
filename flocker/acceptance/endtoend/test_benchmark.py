# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for ``flocker-benchmark``.
"""

import json

from ...common.runner import run_ssh
from ...testtools import AsyncTestCase, async_runner
from ..testtools import require_cluster, ACCEPTANCE_TEST_TIMEOUT


class BenchmarkTests(AsyncTestCase):
    """
    Tests for ``flocker-benchmark``.
    """

    run_tests_with = async_runner(timeout=ACCEPTANCE_TEST_TIMEOUT)

    @require_cluster(1)
    def test_export(self, cluster):
        """
        ``flocker-benchmark hardware-report`` prints a JSON representation of
        the hardware on a benchmark node.
        """
        node_address = cluster.control_node.public_address

        def run_report():
            output = []
            return run_ssh(
                self.reactor,
                'root',
                node_address,
                ['flocker-benchmark', 'hardware-report'],
                handle_stdout=output.append
            ).addCallback(
                lambda ignored: b''.join(output)
            )
        reporting = run_report()

        def check_report(report_bytes):
            json.loads(report_bytes)
        checking = reporting.addCallback(check_report)
        return checking
