# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Test for real world behaviour of Cinder implementations to validate some of our
basic assumptions/understandings of how Cinder works in the real world.
"""

from unittest import SkipTest

from ..cinder import (
    get_keystone_session, get_cinder_v1_client, wait_for_volume_state
)
from ..test.blockdevicefactory import (
    InvalidConfig,
    ProviderType,
    get_openstack_region_for_test,
    get_blockdevice_config,
)
from ....testtools import TestCase, random_name

from .logging import CINDER_VOLUME


def cinder_volume_manager():
    """
    Get an ``ICinderVolumeManager`` configured to work on this environment.

    XXX: It will not automatically clean up after itself. See FLOC-1824.
    """
    try:
        config = get_blockdevice_config(ProviderType.openstack)
    except InvalidConfig as e:
        raise SkipTest(str(e))
    region = get_openstack_region_for_test()
    session = get_keystone_session(**config)
    return get_cinder_v1_client(session, region).volumes


# All of the following tests could be part of the suite returned by
# ``make_icindervolumemanager_tests`` instead.
# https://clusterhq.atlassian.net/browse/FLOC-1846

class VolumesCreateTests(TestCase):
    """
    Tests for ``cinder.Client.volumes.create``.
    """
    def setUp(self):
        super(VolumesCreateTests, self).setUp()
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
        self.cinder_volumes = cinder_volume_manager()

    def test_updated_metadata_is_listed(self):
        """
        ``metadata`` supplied to update_metadata is included when that
        volume is subsequently listed.
        """
        expected_metadata = {random_name(self): u"bar"}

        new_volume = self.cinder_volumes.create(size=100)
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
