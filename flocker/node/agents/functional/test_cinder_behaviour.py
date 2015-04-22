# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for cinder API behaviour.
"""

import uuid
from unittest import TestCase

from ..testtools import require_cinder_credentials
from ..cinder import authenticated_cinder_client

def random_name():
    """
    Return a random unicode label.
    """
    return unicode(uuid.uuid4())


@require_cinder_credentials
def cinder_client_from_environment(OPENSTACK_API_USER, OPENSTACK_API_KEY):
    """
    Create a ``cinder.client.Client`` using credentials from the process
    environment which are supplied to the RackspaceAuth plugin.
    """
    return authenticated_cinder_client(
        username=OPENSTACK_API_USER,
        api_key=OPENSTACK_API_KEY,
        region='DFW',
    )


def wait_for_volume(client, new_volume):
    """
    Wait for a volume with the same id as ``new_volume`` to be listed as
    ``available`` and return that listed volume.
    """
    while True:
        for listed_volume in client.volumes.list():
            if listed_volume.id == new_volume.id:
                if listed_volume.status == 'available':
                    return listed_volume
                else:
                    print "STATUS", listed_volume.status
                    print "METADATA", listed_volume.metadata


class VolumesCreateTests(TestCase):
    """
    Tests for ``cinder.Client.volumes.create``.
    """
    def test_create_metadata_is_listed(self):
        """
        ``metadata`` supplied when creating a volume is included when that
        volume is subsequently listed.
        """
        client = cinder_client_from_environment()

        expected_metadata = {random_name(): "bar"}

        new_volume = client.volumes.create(
            size=100,
            metadata=expected_metadata
        )
        listed_volume = wait_for_volume(client, new_volume)

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
    def test_updated_metadata_is_listed(self):
        """
        ``metadata`` supplied to update_metadata is included when that
        volume is subsequently listed.
        """
        client = cinder_client_from_environment()

        expected_metadata = {random_name(): u"bar"}

        new_volume = client.volumes.create(size=100,)

        listed_volume = wait_for_volume(client, new_volume)

        client.volumes.set_metadata(new_volume, expected_metadata)

        listed_volume = wait_for_volume(client, new_volume)

        expected_items = set(expected_metadata.items())
        actual_items = set(listed_volume.metadata.items())
        missing_items = expected_items - actual_items

        self.assertEqual(set(), missing_items)
