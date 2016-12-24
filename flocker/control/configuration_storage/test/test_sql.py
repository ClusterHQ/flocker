# Copyright ClusterHQ Inc.  See LICENSE file for details.
"""
Tests for ``flocker.control.configuration_storage.sql``.
"""
from ....testtools import AsyncTestCase
from ..testtools import mariadb_server_for_test, IConfigurationStoreTestsMixin
from ..sql import SQLConfigurationStore, NotFound


class SQLTests(IConfigurationStoreTestsMixin, AsyncTestCase):
    def setUp(self):
        super(SQLTests, self).setUp()
        connection_url = mariadb_server_for_test(self)
        self.store = SQLConfigurationStore(
            connection_string=unicode(connection_url)
        )

    def test_uninitialized(self):
        """
        ``get_content`` raises ``NotFound`` if the configuration store key does
        not exist.
        """
        d = self.store.get_content()
        d = self.assertFailure(d, NotFound)
        return d
