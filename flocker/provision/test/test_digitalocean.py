# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for ``flocker.provision._digitalocean``.
"""
import copy
import os
from unittest import skipUnless

try:
    import pyocean
except ImportError:
    PYOCEAN_INSTALLED = False
else:
    PYOCEAN_INSTALLED = True

from twisted.trial.unittest import SynchronousTestCase, SkipTest

from flocker.provision._digitalocean import (
    retry_on_error, pending_event, latest_droplet_kernel, DIGITALOCEAN_KERNEL)
from flocker.testtools import random_name


TESTING_DROPLET_ATTRIBUTES = {
    'region': 'lon1',
    'size': '8gb',
    'image': 'fedora-20-x64'
}


@skipUnless(PYOCEAN_INSTALLED, "digitalocean-python not installed")
def client_from_environment():
    """
    Search the process environment for a DigitalOcean v2 API token and use it
    to build an API client instance.

    :returns: A ``pyocean.DigitalOcean`` client instance.
    """
    token = os.environ.get('DIGITALOCEAN_TOKEN')
    if token is None:
        raise SkipTest(
            'A DIGITALOCEAN_TOKEN environment variable is required to run '
            'these tests.')

    return pyocean.DigitalOcean(token)


def droplet_for_test(test_case, client):
    """
    Update a prototype set of droplet attributes with a random name and make
    API calls to create the droplet.

    :param TestCase test_case: The test for which to build and cleanup the
        droplet.
    :param pyocean.DigitalOcean client: The client with which to make
         DigitalOcean v2 API calls.
    :returns: A ``pyocean.Droplet`` instance.
    """
    droplet_attributes = copy.deepcopy(TESTING_DROPLET_ATTRIBUTES)
    droplet_attributes['name'] = (
        test_case.id().replace('_', '-')
        + '-'
        + random_name()
    )
    droplet = retry_on_error(
        [pending_event],
        client.droplet.create, droplet_attributes
    )
    test_case.addCleanup(retry_on_error, [pending_event], droplet.destroy)
    return droplet


class LatestDropletKernelTests(SynchronousTestCase):
    """
    Tests for ``latest_droplet_kernel``.

    These tests are designed to interact with live DigitalOcean droplets.

    You must supply a DigitalOcean V2 API token by setting
    ``DIGITALOCEAN_TOKEN`` in the environment before running these tests.
    """
    def setUp(self):
        """
        Set up a test droplet and destroy it after the test.
        """
        self.client = client_from_environment()
        self.droplet = droplet_for_test(self, self.client)

    def test_success(self):
        """
        ``latest_droplet_kernel`` should return the same kernel that we ask
        users to install in our documentation.
        """
        expected_kernel = DIGITALOCEAN_KERNEL
        actual_kernel = latest_droplet_kernel(self.droplet, 'fc20', 'x86_64')

        self.assertEqual(expected_kernel, actual_kernel)
