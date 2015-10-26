# Copyright 2015 ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for ``flocker.node.agents.cinder``.
"""

from twisted.trial.unittest import SynchronousTestCase

from ..cinder import (
    _openstack_verify_from_config, CinderBlockDeviceAPI,
    TimeoutException, ICinderVolumeManager
    )

from zope.interface import Interface, implementer

from uuid import uuid4

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
        HTTPS connections are verified using a CA bundle if
        ``verify_ca_path`` is provided.
        """
        config = {
            'backend': 'openstack',
            'auth_plugin': 'password',
            'verify_peer': True,
            'verify_ca_path': '/a/path'
        }
        self.assertEqual(_openstack_verify_from_config(**config), '/a/path')

    def test_verify_false(self):
        """
        HTTPS connections are not verified if ``verify_peer`` is false.
        """
        config = {
            'backend': 'openstack',
            'auth_plugin': 'password',
            'verify_peer': False,
        }
        self.assertEqual(_openstack_verify_from_config(**config), False)

    def test_verify_false_ca_path(self):
        """
        HTTPS connections are not verified if ``verify_peer`` is false,
        even if a ``verify_ca_path`` is provided.
        """
        config = {
            'backend': 'openstack',
            'auth_plugin': 'password',
            'verify_peer': False,
            'verify_ca_path': '/a/path'
        }
        self.assertEqual(_openstack_verify_from_config(**config), False)


@implementer(ICinderVolumeManager)
class FakeCinderClient(object):
    def delete(self, volume_id):
        """
        A no-op delete
        """

    def get(self, volume_id):
        """
        A no-op get.
        """


class CinderDestroyTests(SynchronousTestCase):
    def test_timeout(self):
        """
        ``CinderBlockDeviceAPI.destroy_volume`` raises
        ``TimeoutException`` if the volume is not removed in 60s.
        """
        fake_cinder = FakeCinderClient()
        cluster_id = uuid4()
        api = CinderBlockDeviceAPI(
            cinder_volume_manager=fake_cinder,
            nova_volume_manager=object(),
            nova_server_manager=object(),
            cluster_id=cluster_id,
        )
        self.assertRaises(
            TimeoutException,
            api.destroy_volume,
            blockdevice_id=u'aaa-bbbb-cccc',
            timeout=1
        )

