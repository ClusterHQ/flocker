# Copyright ClusterHQ Inc.  See LICENSE file for details.
"""
Tests for ``flocker.control.configuration_storage``.
"""
from subprocess import check_output

from zope.interface.verify import verifyObject

from ...testtools import random_name, find_free_port

from .interface import IConfigurationStore


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


class IConfigurationStoreTestsMixin(object):
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
