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
    set_droplet_kernel, retry_on_error, pending_event, latest_droplet_kernel,
    kernel_from_digitalocean_version, DIGITALOCEAN_KERNEL)
from flocker.testtools import random_name


TESTING_DROPLET_ATTRIBUTES = {
    'region': 'lon1',
    'size': '8gb',
    'image': 'fedora-20-x64'
}


@skipUnless(PYOCEAN_INSTALLED, "pyocean not installed")
def client_from_environment():
    token = os.environ.get('DIGITALOCEAN_TOKEN')
    if token is None:
        raise SkipTest(
            'A DIGITALOCEAN_TOKEN environment variable is required to run '
            'these tests.')

    return pyocean.DigitalOcean(token)


def droplet_for_test(test_case, client):
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


class SetDropletKernelTests(SynchronousTestCase):
    """
    Tests for ``set_droplet_kernel``.

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
        ``set_droplet_kernel`` assigns the supplied kernel to the droplet.
        to the droplet, returning the selected DigitalOcean kernel instance.
        """
        expected_kernel = DIGITALOCEAN_KERNEL
        set_droplet_kernel(self.droplet, expected_kernel)

        # Need to query again for the droplet after updating its kernel
        updated_droplet = self.client.droplet.get(self.droplet.id)
        # Pyocean wraps kernel attributes in its ``Image`` class...which makes
        # no sense and then uses a ``dict`` for the ``droplet.kernel``
        # attribute, so they can't be directly compared. It would be better if
        # both used a dedicated ``Kernel`` type which could easily be
        # compared.
        # See: https://github.com/flowfree/pyocean/issues/2
        actual_kernel = kernel_from_digitalocean_version(
            updated_droplet.kernel['version']
        )
        self.assertEqual(expected_kernel, actual_kernel)


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
