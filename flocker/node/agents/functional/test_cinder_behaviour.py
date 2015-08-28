# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Test for real world behaviour of Cinder implementations to validate some of our
basic assumptions/understandings of how Cinder works in the real world.
"""
import time

from twisted.python.filepath import FilePath
from twisted.trial.unittest import SkipTest, SynchronousTestCase

from ..cinder import wait_for_volume, _compute_instance_id
from ..test.blockdevicefactory import (
    InvalidConfig, ProviderType, get_blockdeviceapi_args,
    get_minimum_allocatable_size,
)
from ....testtools import random_name


def cinder_volume_manager():
    """
    Get an ``ICinderVolumeManager`` configured to work on this environment.

    XXX: It will not automatically clean up after itself. See FLOC-1824.
    """
    try:
        cls, kwargs = get_blockdeviceapi_args(ProviderType.openstack)
    except InvalidConfig as e:
        raise SkipTest(str(e))
    return kwargs["cinder_client"].volumes


def nova():
    """
    Get a Nova client for use in tests.
    """
    try:
        cls, kwargs = get_blockdeviceapi_args(ProviderType.openstack)
    except InvalidConfig as e:
        raise SkipTest(str(e))
    return kwargs["nova_client"]


# All of the following tests could be part of the suite returned by
# ``make_icindervolumemanager_tests`` instead.
# https://clusterhq.atlassian.net/browse/FLOC-1846

class VolumesCreateTests(SynchronousTestCase):
    """
    Tests for ``cinder.Client.volumes.create``.
    """
    def setUp(self):
        self.cinder_volumes = cinder_volume_manager()

    def test_create_metadata_is_listed(self):
        """
        ``metadata`` supplied when creating a volume is included when that
        volume is subsequently listed.
        """
        expected_metadata = {random_name(self): "bar"}

        new_volume = self.cinder_volumes.create(
            size=100,
            metadata=expected_metadata
        )
        self.addCleanup(self.cinder_volumes.delete, new_volume)
        listed_volume = wait_for_volume(
            volume_manager=self.cinder_volumes,
            expected_volume=new_volume,
        )

        expected_items = set(expected_metadata.items())
        actual_items = set(listed_volume.metadata.items())
        missing_items = expected_items - actual_items
        self.assertEqual(
            set(), missing_items,
            'Metadata {!r} does not contain the expected items {!r}'.format(
                actual_items, expected_items
            )
        )


class VolumesSetMetadataTests(SynchronousTestCase):
    """
    Tests for ``cinder.Client.volumes.set_metadata``.
    """
    def setUp(self):
        self.cinder_volumes = cinder_volume_manager()

    def test_updated_metadata_is_listed(self):
        """
        ``metadata`` supplied to update_metadata is included when that
        volume is subsequently listed.
        """
        expected_metadata = {random_name(self): u"bar"}

        new_volume = self.cinder_volumes.create(size=100)
        self.addCleanup(self.cinder_volumes.delete, new_volume)

        listed_volume = wait_for_volume(
            volume_manager=self.cinder_volumes,
            expected_volume=new_volume,
        )

        self.cinder_volumes.set_metadata(new_volume, expected_metadata)

        listed_volume = wait_for_volume(
            volume_manager=self.cinder_volumes,
            expected_volume=new_volume
        )

        expected_items = set(expected_metadata.items())
        actual_items = set(listed_volume.metadata.items())
        missing_items = expected_items - actual_items

        self.assertEqual(set(), missing_items)


class DevicePathTests(SynchronousTestCase):
    """
    Tests for ``nova.Client.volumes.attach_volume`` and the reporting of device
    paths.
    """
    def setUp(self):
        self.cinder = cinder_volume_manager()
        self.nova = nova()

    def test_maximum_attached_volumes(self):
        """
        ``nova.Client.volumes.attach_volume`` until attachment fails.
        """
        this_instance_id = _compute_instance_id(
            servers=self.nova.servers.list()
        )
        for i in range(1, 15):
            attached_volume = verify_attachment(
                test=self,
                instance_id=this_instance_id
            )
            print "VOLUME: ", i, attached_volume


def _detach(test, instance_id, volume):
    test.nova.volumes.delete_server_volume(instance_id, volume.id)
    return wait_for_volume(
        volume_manager=test.nova.volumes,
        expected_volume=volume,
        expected_status=u'available',
    )


def _cleanup(test, instance_id, volume):
    volume.get()
    if volume.attachments:
        _detach(test, instance_id, volume)
    test.cinder.delete(volume.id)


def volume_for_test(test, instance_id):
    """
    Create a cinder volume and remove it when the test completes.
    Detach it first if necessary.
    """
    volume = test.cinder.create(
        size=int(Byte(get_minimum_allocatable_size()).to_GiB().value)
    )
    test.addCleanup(_cleanup, test, instance_id, volume)
    listed_volume = wait_for_volume(
        volume_manager=test.cinder,
        expected_volume=volume,
    )
    return listed_volume


def verify_attachment(test, instance_id):
    """
    Create and attach a cinder volume.
    Wait 15s for a new device to appear in the OS.
    Then assert that the new device matches the device name reported by cinder.
    """
    volume = volume_for_test(test, instance_id)
    devices_before = set(FilePath('/dev').children())

    attached_volume = test.nova.volumes.create_server_volume(
        server_id=instance_id,
        volume_id=volume.id,
        device=None,
    )
    start_time = time.time()

    while (time.time() - start_time) < 15:
        devices_after = set(FilePath('/dev').children())

        new_devices = devices_after - devices_before

        if new_devices:
            in_use_volume = wait_for_volume(
                volume_manager=test.nova.volumes,
                expected_volume=attached_volume,
                expected_status=u'in-use',
            )

            [attachment] = in_use_volume.attachments
            [new_device] = new_devices
            test.assertEqual(FilePath(attachment['device']), new_device)
            return in_use_volume
        else:
            time.sleep(0.1)
    else:
        attached_volume.get()
        test.fail(
            'Volume Attach Timeout. '
            'After: {!r}, '
            'Volume: {!r}, '
            'Attachments: {!r}, '
            'Devices Before: {!r}, '
            'Devices After: {!r}'.format(
                time.time() - start_time,
                attached_volume,
                attached_volume.attachments,
                [d for d in devices_before if d.path.startswith('/dev/vd')],
                [d for d in FilePath('/dev').children() if d.path.startswith('/dev/vd')],
            )
        )
