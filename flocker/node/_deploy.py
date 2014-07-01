# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
# -*- test-case-name: flocker.node.test.test_deploy -*-

"""
Deploy applications on nodes.
"""

class Deployment(object):
    """
    """
    _gear_client = None

    def start_container(self, application):
        """
        Launch the supplied application as a `gear` unit.
        """

    def stop_container(self, application):
        """
        Stop and disable the application.
        """
