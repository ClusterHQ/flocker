# Copyright 2015 ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for ``flocker.node.agents.cinder``.
"""

from twisted.trial.unittest import SynchronousTestCase

from ..cinder import _openstack_verify_from_config


class VerifyTests(SynchronousTestCase):
    """
    Tests for _openstack_verify_from_config.
    """

    def test_verify_not_set(self):
        """
        HTTPS connections are verified using system CA's if not
        overridden.
        """
        config = {
            'backend': 'openstack',
            'auth_plugin': 'password',
        }
        self.assertEqual(_openstack_verify_from_config(**config), True)

    def test_verify_ca_path(self):
        """
        HTTPS connections are verified using a CA bundle if ca_path is
        provided.
        """
        config = {
            'backend': 'openstack',
            'auth_plugin': 'password',
            'peer_verify': True,
            'ca_path': '/a/path'
        }
        self.assertEqual(_openstack_verify_from_config(**config), '/a/path')

    def test_verify_false(self):
        """
        HTTPS connections are not verified if peer_verify is false.
        """
        config = {
            'backend': 'openstack',
            'auth_plugin': 'password',
            'peer_verify': False,
        }
        self.assertEqual(_openstack_verify_from_config(**config), False)

    def test_verify_false_ca_path(self):
        """
        HTTPS connections are not verified if peer_verify is false, even
        if a ca_path is provided.
        """
        config = {
            'backend': 'openstack',
            'auth_plugin': 'password',
            'peer_verify': False,
            'ca_path': '/a/path'
        }
        self.assertEqual(_openstack_verify_from_config(**config), False)

