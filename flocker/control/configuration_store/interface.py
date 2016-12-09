# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Interface for cluster configuration storage plugin.
"""
from base64 import b16encode
from mmh3 import hash_bytes as mmh3_hash_bytes
from pyrsistent import PClass, field
from zope.interface import Interface


class Content(PClass):
    data = field(type=(bytes,), mandatory=True)

    @property
    def hash(self):
        return b16encode(mmh3_hash_bytes(self.data)).lower()


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

        :returns: A ``Deferred`` that fires with ``Content`` when the store has
        been initialized or with a ``Failure`` if initialization fails.
        """

    def get_content():
        """
        :returns: A ``Deferred`` that fires with a ``Content`` containing
            current Flocker configuration ``bytes``.
        """

    def set_content(last_known_hash, content):
        """
        :param bytes content: New Flocker configuration ``bytes`` to be stored.
        :returns: A ``Deferred`` that fires with ``None`` when the supplied
            Flocker configuration ``bytes`` have been stored.
        """
