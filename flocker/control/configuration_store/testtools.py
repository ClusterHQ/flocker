# Copyright ClusterHQ Inc.  See LICENSE file for details.
"""
Tests for ``flocker.control.configuration_storage``.
"""
from twisted.internet.defer import succeed

from zope.interface import implementer
from zope.interface.verify import verifyObject

from ...testtools import random_name
from .interface import IConfigurationStore


@implementer(IConfigurationStore)
class MemoryConfigurationStore(object):
    _content = None

    def initialize(self):
        if self._content is None:
            self._content = b''
        return succeed(None)

    def get_content(self):
        return succeed(self._content)

    def set_content(self, content):
        self._content = content
        return succeed(None)


class IConfigurationStoreTestsMixin(object):
    """
    Tests for implementers of ``IConfigurationStore``.
    """
    def test_interface(self):
        """
        ``self.store`` provides ``IConfigurationStore``.
        """
        self.assertTrue(verifyObject(IConfigurationStore, self.store))

    def test_initialize_returns_none(self):
        """
        ``initialize`` returns ``None``.
        """
        d = self.store.initialize()
        d.addCallback(self.assertIs, None)
        return d

    def test_initialize_empty(self):
        """
        ``initialize`` creates the key with an empty value.
        """
        d = self.store.initialize()
        d.addCallback(lambda ignored: self.store.get_content())
        d.addCallback(self.assertEqual, b"")
        return d

    def test_set_and_get(self):
        """
        ``set_content`` sets the value and the value can be retrieved by
        ``get_content``.
        """
        expected_value = random_name(self).encode('utf8')
        d = self.store.initialize()
        d.addCallback(lambda ignored: self.store.set_content(expected_value))
        d.addCallback(lambda ignored: self.store.get_content())
        d.addCallback(self.assertEqual, expected_value)
        return d

    def test_initialize_non_empty(self):
        """
        ``initialize`` does not overwrite an existing value.
        """
        expected_value = random_name(self).encode('utf8')
        d = self.store.initialize()
        d.addCallback(lambda ignored: self.store.set_content(expected_value))
        # Second initialize does not overwrite the expected_value above.
        d.addCallback(lambda ignored: self.store.initialize())
        d.addCallback(lambda ignored: self.store.get_content())
        d.addCallback(self.assertEqual, expected_value)
        return d
