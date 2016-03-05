# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Test for real world behaviour of Cinder implementations to validate some of our
basic assumptions/understandings of how Cinder works in the real world.
"""
from itertools import repeat
from unittest import SkipTest

from bitmath import Byte

from ..cinder import (
    get_keystone_session, get_cinder_client, wait_for_volume_state
)
from ..test.blockdevicefactory import (
    InvalidConfig,
    ProviderType,
    get_openstack_region_for_test,
    get_blockdevice_config,
    get_minimum_allocatable_size,
)
from ....common import poll_until
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
        self.cinder_volumes = cinder_volume_manager()

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


def delete_multiple_volumes(cinder_volume_manager, volumes):
    for volume in volumes:
        cinder_volume_manager.delete(volume)

    deleted_volume_ids = set(v.id for v in volumes)
    def all_gone():
        found_volume_ids = set(
            v.id for v in cinder_volume_manager.list()
        )
        return len(deleted_volume_ids.intersection(found_volume_ids)) == 0
    return poll_until(all_gone, repeat(1, 60))


class CinderPagingTests(TestCase):
    """
    Tests for Cinder V2 paging.

    These tests will only work on an OpenStack server where Cinder API
    has been configured with ``osapi_max_limit = 5``.

    To configure devstack this way, add the following to ``local.conf``:

    ```
    [[post-config|$CINDER_CONF]] 
    [DEFAULT]                    
    osapi_max_limit = 5
    ```
    """

    def _create_volumes(self, client, volume_count):
        """
        Create multiple volumes, wait for them to be available and
        clean them all up after the test, blocking until they have
        been deleted.

        :param cinderclient.client.Client client: The Cinder client to use.
        :param int volume_count: The number of volumes to create.
        :returns: The ``list`` of volumes created.
        """
        volumes = list(
            client.create(
                size=int(Byte(get_minimum_allocatable_size()).to_GiB().value)
            )
            for i in range(volume_count)
        )

        list(CINDER_VOLUME(id=v.id).write() for v in volumes)

        self.addCleanup(
            delete_multiple_volumes, 
            cinder_volume_manager=client,
            volumes=volumes
        )

        list(
            wait_for_volume_state(
                volume_manager=client,
                expected_volume=v,
                desired_state=u'available',
                transient_states=(u'creating',),
            )
            for v in volumes
        )
        return volumes

    def test_unpaged_v1(self):
        """
        Cinder v1 client does not handle paged API responses so if we
        set the ``osapi_max_limit = 5`` the Cinder API server will
        only return 2 results at a time and the Cinder v1 client will
        only report the first two.
        """
        client = cinder_volume_manager(version=1)
        self._create_volumes(client, 10)
        self.assertEqual(5, len(client.list()))

    def test_paged_v2(self):
        """
        Cinder v2 client does handle paged API responses so if we
        set the ``osapi_max_limit = 5`` the Cinder API server will
        return all the results.
        """
        client = cinder_volume_manager(version=2)
        volumes = self._create_volumes(client, 10)
        self.assertEqual(
            set(v.id for v in volumes), 
            set(v.id for v in client.list())
        )
