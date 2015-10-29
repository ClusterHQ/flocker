# Copyright 2015 ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for ``flocker.node.agents.cinder``.
"""

from twisted.trial.unittest import SynchronousTestCase

from ..cinder import (
    _openstack_verify_from_config, CinderBlockDeviceAPI,
    TimeoutException
    )

from uuid import uuid4
from ..blockdevice import BlockDeviceVolume


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


class FakeCinderClient(object):
    """"
    Fake implementation of the cinder volume manager to use in the Cinder
    Destroy tests.
    Right now, we don't need a full fake of the class, we just need the
    get not to raise any exception so the destroy volume timeout test
    actually times out - it will be trying to get the volume in a loop
    after deleting it, expecting a ``CinderNotFound`` exception that will
    never happen, so we can verify that the timeout exception is rised
    (see FLOC-1853)
    """
    def delete(self, volume_id):
        """
        A no-op delete.
        We do not need the delete to do anything for the timeout tests.
        """

    def get(self, volume_id):
        """
        A no-op get.
        Return a fake BlockDeviceVolume
        """
        return BlockDeviceVolume(
            size=100, attached_to=None,
            dataset_id=uuid4(),
            blockdevice_id=unicode(volume_id),
        )


class CinderDestroyTests(SynchronousTestCase):
    """
    Tests for destroy_volume.
    Test added with the fix of the issue FLOC-1853
    """

    def test_timeout(self):
        """
        ``CinderBlockDeviceAPI.destroy_volume`` raises
        ``TimeoutException`` if the volume is not removed within
        some time.
        """
        # Uses the fake implementation of the Cinder Volume that will
        # be unresponsive.
        api = CinderBlockDeviceAPI(
            cinder_volume_manager=FakeCinderClient(),
            nova_volume_manager=object(),
            nova_server_manager=object(),
            cluster_id=uuid4()
        )
        # Timeout = 1 because the default timeout is 300 secods, and
        # it is a bit too long for a test that runs regularly under CI
        returnedBlockDevice = FakeCinderClient().get(uuid4())
        if not isinstance(returnedBlockDevice, BlockDeviceVolume):
            self.fail("returned block device is not a BlockDeviceVolume")
        api.timeout = 1
        self.assertRaises(
            TimeoutException,
            api.destroy_volume,
            blockdevice_id=unicode(uuid4())
        )
