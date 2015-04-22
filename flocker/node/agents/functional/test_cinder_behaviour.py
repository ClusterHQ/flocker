# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for cinder API behaviour.
"""

from twisted.trial.unittest import SynchronousTestCase

from ..cinder import wait_for_volume
from ..testtools import tidy_cinder_client_for_test
from ....testtools import random_name


class VolumesCreateTests(SynchronousTestCase):
    """
    Tests for ``cinder.Client.volumes.create``.
    """
    def setUp(self):
        self.cinder_client = tidy_cinder_client_for_test(test_case=self)

    def test_create_metadata_is_listed(self):
        """
        ``metadata`` supplied when creating a volume is included when that
        volume is subsequently listed.
        """
        expected_metadata = {random_name(): "bar"}

        new_volume = self.cinder_client.volumes.create(
            size=100,
            metadata=expected_metadata
        )
        listed_volume = wait_for_volume(self.cinder_client, new_volume)

        expected_items = set(expected_metadata.items())
        actual_items = set(listed_volume.metadata.items())
        missing_items = expected_items - actual_items
        self.assertEqual(
            set(), missing_items,
            'Metadata {!r} does not contain the expected items {!r}'.format(
                actual_items, expected_items
            )
        )
    test_create_metadata_is_listed.todo = (
        'Rackspace API does not save the supplied metadata. '
        'See support ticket: 150422-ord-0000495'
    )


class VolumesSetMetadataTests(SynchronousTestCase):
    """
    Tests for ``cinder.Client.volumes.set_metadata``.
    """
    def setUp(self):
        self.cinder_client = tidy_cinder_client_for_test(test_case=self)

    def test_updated_metadata_is_listed(self):
        """
        ``metadata`` supplied to update_metadata is included when that
        volume is subsequently listed.
        """
        expected_metadata = {random_name(): u"bar"}

        new_volume = self.cinder_client.volumes.create(size=100,)

        listed_volume = wait_for_volume(self.cinder_client, new_volume)

        self.cinder_client.volumes.set_metadata(new_volume, expected_metadata)

        listed_volume = wait_for_volume(self.cinder_client, new_volume)

        expected_items = set(expected_metadata.items())
        actual_items = set(listed_volume.metadata.items())
        missing_items = expected_items - actual_items

        self.assertEqual(set(), missing_items)
