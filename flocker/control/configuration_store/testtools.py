# Copyright ClusterHQ Inc.  See LICENSE file for details.
"""
Tests for ``flocker.control.configuration_storage``.
"""
from twisted.internet.defer import succeed, inlineCallbacks, returnValue

from zope.interface import implementer
from zope.interface.verify import verifyObject

from ...testtools import random_name, AsyncTestCase

from .interface import IConfigurationStore, Content


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

    def test_initialize_returns_content(self):
        """
        ``initialize`` returns ``Content`` with empty bytes when it is first
        called.
        """
        d = self.store.initialize()
        d.addCallback(self.assertEqual, Content(data=b""))
        return d

    @inlineCallbacks
    def test_set_and_get(self):
        """
        ``set_content`` sets the value and the value can be retrieved by
        ``get_content``.
        """
        expected_value = random_name(self).encode('utf8')
        content = yield self.store.initialize()
        new_hash = yield self.store.set_content(content.hash, expected_value)
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

    # @inlineCallbacks
    # def test_locking(self):
    #     store1 = self.store_factory(self)
    #     store2 = self.store_factory(self)
    #     store1_initial_hash = yield store1.initialize()
    #     store2_initial_hash = yield store2.initialize()
    #     result1 = yield store1.set_content(b"store1_content")
    #     result2 = yield store2.set_content(b"store2_content")
    #     self.assertEqual()




def make_iconfigurationstore_tests(store_factory):
    class Tests(IConfigurationStoreTestsMixin, AsyncTestCase):
        def setUp(self):
            super(Tests, self).setUp()
            self.store_factory = store_factory
            self.store = store_factory(self)
    return Tests
