# Copyright ClusterHQ Inc.  See LICENSE file for details.
"""
Tests for ``flocker.control.configuration_storage.consul``.
"""
from twisted.internet import reactor
from twisted.internet.error import ConnectionRefusedError

from ....testtools import AsyncTestCase
from ....common import retry_failure
from ..testtools import consul_server_for_test, IConfigurationStoreTestsMixin
from ..consul import ConsulConfigurationStore, NotFound, NotReady


class ConsulTests(IConfigurationStoreTestsMixin, AsyncTestCase):
    def setUp(self):
        super(ConsulTests, self).setUp()
        api_port = consul_server_for_test(self)
        self.store = ConsulConfigurationStore(
            api_port=api_port
        )
        return retry_failure(
            reactor,
            self.store._ready,
            {ConnectionRefusedError, NotReady},
            [0.1] * 50
        )

    def test_uninitialized(self):
        """
        ``get_content`` raises ``NotFound`` if the configuration store key does
        not exist.
        """
        d = self.store.get_content()
        d = self.assertFailure(d, NotFound)
        return d
