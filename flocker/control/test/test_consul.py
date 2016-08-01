# Copyright ClusterHQ Inc.  See LICENSE file for details.
"""
Tests for ``flocker.control._consul``.
"""
from subprocess import check_output

from twisted.internet import reactor
from twisted.internet.error import ConnectionRefusedError

from ...testtools import AsyncTestCase, random_name, find_free_port
from ...common import retry_failure
from .._consul import ConsulConfigurationStore, NotFound, NotReady


def consul_server_for_test(test_case):
    api_address, api_port = find_free_port()
    container_name = random_name(test_case)
    container_id = check_output([
        'docker', 'run',
        '--detach',
        '--net', 'host',
        '--name', container_name,
        'consul',
        'agent',
        '-advertise', '127.0.0.1',
        '-http-port', str(api_port),
        '-dev'
    ]).rstrip()

    test_case.addCleanup(
        check_output,
        ['docker', 'rm', '--force', container_id]
    )
    return api_port


class ConsulTests(AsyncTestCase):
    def setUp(self):
        super(ConsulTests, self).setUp()
        api_port = consul_server_for_test(self)
        self.store = ConsulConfigurationStore(
            api_port=api_port
        )
        return retry_failure(
            reactor,
            self.store.ready,
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
