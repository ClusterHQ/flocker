# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for communication to applications.
"""
from twisted.trial.unittest import TestCase


class PortsTests(TestCase):
    """
    Tests for communication to applications.

    Similar to http://doc-dev.clusterhq.com/gettingstarted/tutorial/
    exposing-ports.html
    """
    def test_traffic_routed(self):
        """
        An application can be accessed even from a connection to a node
        which it is not running on.
        """
        # Deploy a database to node1
        # add data to this database
        # connect to the node where it is not running
