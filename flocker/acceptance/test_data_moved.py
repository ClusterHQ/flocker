# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for movement of data across nodes.
"""

class DataTests(TestCase):
    """
    Tests for movement of data across nodes.

    Similar to http://doc-dev.clusterhq.com/gettingstarted/tutorial/volumes.html
    """
    def test_data_moves(self):
        """
        Moving an application moves data with it.
        """
        # Deploy a database to node1
        # add data to this database
        # Move the application to node 2
        # Check that the data is available on node 2