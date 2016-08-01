# Copyright ClusterHQ Inc.  See LICENSE file for details.
"""
Tests for ``flocker.control._consul``.
"""
from subprocess import check_output
import time

from ...testtools import AsyncTestCase, random_name

from .._consul import ConsulConfigurationStore, NotFound


def consul_server_for_test(test_case):
    container_name = random_name(test_case)
    container_id = check_output([
        'docker', 'run',
        '--detach',
        '--net', 'host',
        '--name', container_name,
        'consul',
        'agent',
        '-advertise', '127.0.0.1',
        '-dev'
    ]).rstrip()

    test_case.addCleanup(
        check_output,
        ['docker', 'rm', '--force', container_id]
    )
    # XXX Wait for consul port to be listening.
    time.sleep(2)


class ConsulTests(AsyncTestCase):
    def setUp(self):
        super(ConsulTests, self).setUp()
        consul_server_for_test(self)

    def test_uninitialized(self):
        """
        ``get_content`` raises ``NotFound`` if the configuration store key does
        not exist.
        """
        store = ConsulConfigurationStore()
        d = store.get_content()
        d = self.assertFailure(d, NotFound)
        return d

    def test_initialize_empty(self):
        """
        ``initialize`` creates the key with an empty value.
        """
        store = ConsulConfigurationStore()
        d = store.initialize()
        d.addCallback(lambda ignored: store.get_content())
        d.addCallback(self.assertEqual, b"")
        return d

    def test_set_and_get(self):
        """
        ``set_content`` sets the value and the value can be retrieved by
        ``get_content``.
        """
        expected_value = random_name(self).encode('utf8')
        store = ConsulConfigurationStore()
        d = store.initialize()
        d.addCallback(lambda ignored: store.set_content(expected_value))
        d.addCallback(lambda ignored: store.get_content())
        d.addCallback(self.assertEqual, expected_value)
        return d

    def test_initialize_non_empty(self):
        """
        ``initialize`` does not overwrite an existing value.
        """
        expected_value = random_name(self).encode('utf8')
        store = ConsulConfigurationStore()
        d = store.initialize()
        d.addCallback(lambda ignored: store.set_content(expected_value))
        d.addCallback(lambda ignored: store.initialize())
        d.addCallback(lambda ignored: store.get_content())
        d.addCallback(self.assertEqual, expected_value)
        return d
