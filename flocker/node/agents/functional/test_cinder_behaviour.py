# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Test for real world behaviour of Cinder implementations to validate some of our
basic assumptions/understandings of how Cinder works in the real world.
"""

from bitmath import Byte

from ..cinder import wait_for_volume_state
from ..test.blockdevicefactory import (
    ProviderType,
    get_minimum_allocatable_size,
    get_blockdeviceapi_with_cleanup,
)
from ....testtools import TestCase, random_name

from .logging import CINDER_VOLUME


# All of the following tests could be part of the suite returned by
# ``make_icindervolumemanager_tests`` instead.
# https://clusterhq.atlassian.net/browse/FLOC-1846

class VolumesCreateTests(TestCase):
    """
    Tests for ``cinder.Client.volumes.create``.
    """
    def setUp(self):
        super(VolumesCreateTests, self).setUp()
        self.cinder_volumes = get_blockdeviceapi_with_cleanup(
            self,
            ProviderType.openstack
        ).cinder_volume_manager

    def test_create_metadata_is_listed(self):
        """
        ``metadata`` supplied when creating a volume is included when that
        volume is subsequently listed.
        """
        expected_metadata = {random_name(self): "bar"}

        new_volume = self.cinder_volumes.create(
            size=int(Byte(get_minimum_allocatable_size()).to_GiB().value),
            metadata=expected_metadata
        )
        CINDER_VOLUME(id=new_volume.id).write()
        self.addCleanup(self.cinder_volumes.delete, new_volume)
        listed_volume = wait_for_volume_state(
            volume_manager=self.cinder_volumes,
            expected_volume=new_volume,
            desired_state=u'available',
            transient_states=(u'creating',),
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


class VolumesSetMetadataTests(TestCase):
    """
    Tests for ``cinder.Client.volumes.set_metadata``.
    """
    def setUp(self):
        super(VolumesSetMetadataTests, self).setUp()
        self.cinder_volumes = get_blockdeviceapi_with_cleanup(
            self,
            ProviderType.openstack
        ).cinder_volume_manager

    def test_updated_metadata_is_listed(self):
        """
        ``metadata`` supplied to update_metadata is included when that
        volume is subsequently listed.
        """
        expected_metadata = {random_name(self): u"bar"}

        new_volume = self.cinder_volumes.create(
            size=int(Byte(get_minimum_allocatable_size()).to_GiB().value),
        )
        CINDER_VOLUME(id=new_volume.id).write()
        self.addCleanup(self.cinder_volumes.delete, new_volume)

        listed_volume = wait_for_volume_state(
            volume_manager=self.cinder_volumes,
            expected_volume=new_volume,
            desired_state=u'available',
            transient_states=(u'creating',),
        )

        self.cinder_volumes.set_metadata(new_volume, expected_metadata)

        listed_volume = wait_for_volume_state(
            volume_manager=self.cinder_volumes,
            expected_volume=new_volume,
            desired_state=u'available',
        )

        expected_items = set(expected_metadata.items())
        actual_items = set(listed_volume.metadata.items())
        missing_items = expected_items - actual_items

        self.assertEqual(set(), missing_items)
