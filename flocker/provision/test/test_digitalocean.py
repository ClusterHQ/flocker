# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for ``flocker.provision._digitalocean``.
"""
import copy
import os

from twisted.trial.unittest import SynchronousTestCase, SkipTest

from flocker.provision._digitalocean import (
    set_latest_droplet_kernel, retry_if_pending)
from flocker.testtools import random_name


TESTING_DROPLET_ATTRIBUTES = {
    'region': 'lon1',
    'size': '8gb',
    'image': 'fedora-20-x64'
}


class LatestDropletKernelTests(SynchronousTestCase):
    def setUp(self):
        """
        Set up a test droplet and destroy it after the test.
        """
        import pyocean

        token = os.environ.get('DIGITALOCEAN_TOKEN')
        if token is None:
            raise SkipTest(
                'A DIGITALOCEAN_TOKEN environment variable is required to run '
                'these tests.')

        client = pyocean.DigitalOcean(token)

        droplet_attributes = copy.deepcopy(TESTING_DROPLET_ATTRIBUTES)
        droplet_attributes['name'] = (
            self.id().replace('_', '-')
            + '-'
            + random_name()
        )
        droplet = retry_if_pending(client.droplet.create, droplet_attributes)
        self.addCleanup(retry_if_pending, droplet.destroy)

        self.client = client
        self.droplet = droplet

    def test_success(self):
        """
        ``set_latest_droplet_kernel`` selects the newest kernel and assigns it
        to the droplet, returning the selected kernel.
        """
        expected_kernel = set_latest_droplet_kernel(self.droplet)

        # Need to query again for the droplet after updating its kernel
        updated_droplet = self.client.droplet.get(self.droplet.id)

        # pyocean wraps kernel attributes in its ``Image`` class...which makes
        # no sense and then uses a ``dict`` for the ``droplet.kernel``
        # attribute, so they can't be directly compared. Just check they have
        # the same ID.
        self.assertEqual(expected_kernel.id, updated_droplet.kernel['id'])
