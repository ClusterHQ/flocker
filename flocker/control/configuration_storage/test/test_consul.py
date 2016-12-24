# Copyright ClusterHQ Inc.  See LICENSE file for details.
"""
Tests for ``flocker.control.configuration_storage.consul``.
"""
from ....testtools import AsyncTestCase
from ..testtools import consul_server_for_test, IConfigurationStoreTestsMixin
from ..consul import ConsulConfigurationStore, NotFound


class ConsulTests(IConfigurationStoreTestsMixin, AsyncTestCase):
    def setUp(self):
        super(ConsulTests, self).setUp()
        api_port = consul_server_for_test(self)
        self.store = ConsulConfigurationStore(
            api_port=api_port
        )

    def test_uninitialized(self):
        """
        ``get_content`` raises ``NotFound`` if the configuration store key does
        not exist.
        """
        d = self.store.get_content()
        d = self.assertFailure(d, NotFound)
        return d
