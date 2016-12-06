# Copyright ClusterHQ Inc.  See LICENSE file for details.
"""
Tests for ``flocker.control.configuration_store.sql``.
"""
from ....testtools import AsyncTestCase

from ..sql import SQLConfigurationStore
from ..testtools import IConfigurationStoreTestsMixin


class SQLConfigurationStoreInterfaceTests(IConfigurationStoreTestsMixin,
                                          AsyncTestCase):
    """
    Tests for ``SQLConfigurationStore``.
    """
    def setUp(self):
        super(SQLConfigurationStoreInterfaceTests, self).setUp()
        self.store = SQLConfigurationStore()
