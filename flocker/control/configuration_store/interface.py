# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Interface for cluster configuration storage plugin.
"""

from zope.interface import Interface


class IConfigurationStore(Interface):
    """
    An interface for initializing, getting and setting Flocker configuration.
    """
    def initialize():
        """
        Set up a configuration store.
        The implementation must be idempotent.
        Calling ``initialize`` on an already initialized store must not change
        the stored configuration.

        :returns: A ``Deferred`` that fires with ``None`` when the store has
        been initialized or with a ``Failure`` if initialization fails.
        """

    def get_content():
        """
        :returns: A ``Deferred`` that fires with the current Flocker
            configuration ``bytes``.
        """

    def set_content(content):
        """
        :param bytes content: New Flocker configuration ``bytes`` to be stored.
        :returns: A ``Deferred`` that fires with ``None`` when the supplied
            Flocker configuration ``bytes`` have been stored.
        """
