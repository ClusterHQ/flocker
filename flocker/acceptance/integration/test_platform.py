# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for integration with the host operating system which runs Flocker.
"""

from ..testtools import require_cluster

from twisted.python.filepath import FilePath
from twisted.trial.unittest import TestCase


class SyslogTests(TestCase):
    """
    Tests for Flocker's integration with syslog.
    """
    def _assert_not_logged(self, fragment):
        getting = cluster.get_file(
            cluster.control_node,
            FilePath(b"/var/log/messages"),
        )

        def got_messages(path):
            with path.open() as messages:
                for line in messages:
                    self.assertNotIn(fragment, line)

        getting.addCallback(got_messages)
        return getting

    @require_cluster(1)
    def test_flocker_control_not_logged(self, cluster):
        """
        Log messages from ``flocker-control`` do not appear in syslog.
        """
        return self._assert_not_logged(b"flocker:controlservice:")

    @require_cluster(1)
    def test_flocker_agent_not_logged(self, cluster):
        """
        Log messages from the Flocker agents do not appear in syslog.
        """
        return self._assert_not_logged(b"flocker:agent:")
