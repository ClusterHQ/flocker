# Copyright ClusterHQ Inc.  See LICENSE file for details.
"""
Tests for ``flocker.control.configuration_store.filepath``.
"""
from ....testtools import AsyncTestCase

from ..testtools import IConfigurationStoreTestsMixin, MemoryConfigurationStore


class MemoryConfigurationStoreInterfaceTests(IConfigurationStoreTestsMixin,
                                             AsyncTestCase):
    """
    Tests for ``MemoryConfigurationStore``.
    """
    def setUp(self):
        super(MemoryConfigurationStoreInterfaceTests, self).setUp()
        self.store = MemoryConfigurationStore()
