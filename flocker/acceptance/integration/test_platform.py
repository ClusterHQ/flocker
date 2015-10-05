# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for integration with the host operating system which runs Flocker.
"""

from ..testtools import require_cluster
from ...common.runner import RemoteFileNotFound

from twisted.python.filepath import FilePath
from twisted.trial.unittest import SkipTest, TestCase


class SyslogTests(TestCase):
    """
    Tests for Flocker's integration with syslog.
    """
    def _assert_not_logged(self, cluster, fragment):
        """
        Assert that the given fragment of a log line does not appear in the
        ``/var/log/messages`` file on the control node of the cluster.
        """
        getting = cluster.get_file(
            cluster.control_node,
            FilePath(b"/var/log/messages"),
        )

        def check_missing_messages(reason):
            reason.trap(RemoteFileNotFound)
            # XXX It would be better to predict this case based on what we know
            # about the OS the cluster is running.  We don't currently have
            # easy access to that information, though.
            #
            # Doing it this way is subject to incorrect skips if we happen to
            # make a mistaken assumption about /var/log/messages (eg if we
            # misspell the name or if it just hasn't been written *quite* yet
            # at the time we check).
            #
            # Currently, CentOS and Ubuntu are supported and CentOS is expected
            # to have this log file and Ubuntu is expected not to.
            raise SkipTest("{} not found".format(reason.value))
        getting.addErrback(check_missing_messages)

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
        # Agents will connect to the control service right away.  This triggers
        # some logging that we'll be able to notice if it is going where we
        # don't want it.
        return self._assert_not_logged(cluster, b"flocker:controlservice:")

    @require_cluster(1)
    def test_flocker_agent_not_logged(self, cluster):
        """
        Log messages from the Flocker agents do not appear in syslog.
        """
        # As above - the agent connects to the control service right away and
        # logs things.
        return self._assert_not_logged(cluster, b"flocker:agent:")
