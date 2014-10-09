# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for moving applications between nodes.
"""
from twisted.trial.unittest import TestCase


class MoveTests(TestCase):
    """
    Tests for moving applications between nodes.

    Similar to http://doc-dev.clusterhq.com/gettingstarted/tutorial/
    moving-applications.html#moving-an-application
    """
    def test_move(self):
        """
        Test moving an application from one node to another.
        """
        # Deploy an application to one node
        # Use a new deployment config to change that application to be on a
        # new node
        # Check that the application is not on the first node, but is on the
        # second node
