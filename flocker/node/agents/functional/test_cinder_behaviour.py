# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Test for real world behaviour of Cinder implementations to validate some of our
basic assumptions/understandings of how Cinder works in the real world.
"""
from itertools import repeat

from bitmath import Byte

from ..cinder import wait_for_volume_state
from ..test.blockdevicefactory import (
    ProviderType,
    get_minimum_allocatable_size,
    get_blockdeviceapi_with_cleanup,
)
from ....common import poll_until
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
        volumes = []
        try:
            for i in range(volume_count):
                v = client.create(
                    size=int(
                        Byte(get_minimum_allocatable_size()).to_GiB().value
                    )
                )
                volumes.append(v)
                CINDER_VOLUME(id=v.id).write()
        finally:
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
        client = get_blockdeviceapi_with_cleanup(
            self,
            ProviderType.openstack
        ).cinder_volume_manager

        self._create_volumes(client, 10)
        self.assertEqual(5, len(client.list()))

    def test_paged_v2(self):
        """
        Cinder v2 client does handle paged API responses so if we
        set the ``osapi_max_limit = 5`` the Cinder API server will
        return all the results.
        """
        client = get_blockdeviceapi_with_cleanup(
            self,
            ProviderType.openstack
        ).cinder_volume_manager

        volumes = self._create_volumes(client, 10)
        self.assertEqual(
            set(v.id for v in volumes),
            set(v.id for v in client.list())
        )
