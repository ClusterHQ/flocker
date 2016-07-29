# Copyright ClusterHQ Inc.  See LICENSE file for details.
"""
Tests for ``flocker.control._consul``.
"""
from subprocess import check_output
import time

from ...testtools import AsyncTestCase, random_name

from .._consul import ConsulConfigurationStore


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
    time.sleep(1)


class ConsulTests(AsyncTestCase):
    def test_get_content_empty(self):
        consul_server_for_test(self)
        store = ConsulConfigurationStore()
        d = store.get_content()
        d.addCallback(self.assertEqual, '')
        return d
