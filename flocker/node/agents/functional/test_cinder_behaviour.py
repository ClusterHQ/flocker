# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Test for real world behaviour of Cinder implementations to validate some of our
basic assumptions/understandings of how Cinder works in the real world.
"""

from unittest import SkipTest

from ..cinder import (
    get_keystone_session, get_cinder_client, wait_for_volume_state
)
from ..test.blockdevicefactory import (
    InvalidConfig,
    ProviderType,
    get_openstack_region_for_test,
    get_blockdevice_config,
)
from ....testtools import TestCase, random_name

from .logging import CINDER_VOLUME


def cinder_volume_manager(version=1):
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
    return get_cinder_client(session, region, version=version).volumes


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


class CinderPagingTests(TestCase):
    """
    Tests for Cinder V2 paging.

    These tests will only work on an OpenStack server where Cinder API
    has been configured with ``osapi_max_limit = 2``.

    To configure devstack this way, add the following to ``local.conf``

        ```
        [[post-config|$CINDER_CONF]] 
        [DEFAULT]                    
        osapi_max_limit = 2          
        ```

    """
    def test_unpaged_v1(self):
        """
        Cinder v1 client does not handle paged API responses so if we
        set the ``osapi_max_limit = 2`` the Cinder API server will
        only return 2 results at a time and the Cinder v1 client will
        only report the first two.
        """
        client = cinder_volume_manager(version=1)

        volumes = list(
            client.create(size=1)
            for i in range(10)
        )

        list(CINDER_VOLUME(id=v.id).write() for v in volumes)

        self.addCleanup(lambda: list(client.delete(v) for v in volumes))

        list(
            wait_for_volume_state(
                volume_manager=client,
                expected_volume=v,
                desired_state=u'available',
                transient_states=(u'creating',),
            )
            for v in volumes
        )
        self.assertEqual(
            5, 
            set(v.id for v in client.list())
        )

    def test_paged_v2(self):
        """
        Cinder v2 client does handle paged API responses so if we
        set the ``osapi_max_limit = 2`` the Cinder API server will
        only return all the results.
        """
        client = cinder_volume_manager(version=2)

        volumes = list(
            client.create(size=1)
            for i in range(10)
        )

        list(CINDER_VOLUME(id=v.id).write() for v in volumes)

        self.addCleanup(lambda: list(client.delete(v) for v in volumes))

        list(
            wait_for_volume_state(
                volume_manager=client,
                expected_volume=v,
                desired_state=u'available',
                transient_states=(u'creating',),
            )
            for v in volumes
        )
        self.assertEqual(
            set(v.id for v in volumes), 
            set(v.id for v in client.list())
        )
