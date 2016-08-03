# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Interface for cluster configuration storage plugin.
"""

from zope.interface import Interface


class IConfigurationStore(Interface):
    """
    """
    def initialize():
        """
        """

    def get_content():
        """
        """

    def set_content(content):
        """
        """
