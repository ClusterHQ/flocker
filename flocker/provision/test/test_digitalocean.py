# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for ``flocker.provision._digitalocean``.
"""

from twisted.trial.unittest import SynchronousTestCase

from flocker.provision._digitalocean import list_kernels


# It would be nice to use libcloud.common.base.JsonResponse instead of defining
# our own response type here.  However, JsonResponse is not very amenable to
# testing.  It wants an HTTPResponse object and it wants to read stuff from
# that object in order to initialize itself.  With this CannedResponse we can
# just pass in some structured data representing the case we want to test.
class CannedResponse(object):
    def __init__(self, expected_response):
        self.object = expected_response


class CannedResponseConnection(object):
    """
    """
    def __init__(self, expected_response):
        self._response = expected_response

    def request(self):
        return CannedResponse(self._response)


class CannedResponseDriver(object):
    def __init__(self, expected_response):
        self._response = expected_response
        self.connection = CannedResponseConnection(expected_response)


class ListKernelsTestsMixin(object):
    def test_all(self):
        """
        """
        actual_kernels = list_kernels(self.driver, droplet_id=object())
        expected_kernels = []
        self.assertEqual(expected_kernels, actual_kernels)


def make_list_kernels_tests(driver):
    class ListKernelTests(ListKernelsTestsMixin, SynchronousTestCase):
        def setUp(self):
            self.driver = driver
    return ListKernelTests


test_driver = CannedResponseDriver(
    expected_response = {
        "kernels": [
          {
            "id": 231,
            "name": "DO-recovery-static-fsck",
            "version": "3.8.0-25-generic"
          }
        ],
        "links": {
          "pages": {
            "last": "https://api.digitalocean.com/v2/droplets/3164494/kernels?page=124&per_page=1",
            "next": "https://api.digitalocean.com/v2/droplets/3164494/kernels?page=2&per_page=1"
          }
        },
        "meta": {
          "total": 124
        }
    }
)

class CannedListKernelsTests(make_list_kernels_tests(test_driver)):
    """
    """


import os
from libcloud.compute.drivers.digitalocean import DigitalOceanNodeDriver
def driver_from_environment():
    """
    """
    client_id = os.environ.get('DIGITALOCEAN_CLIENT_ID')
    api_key = os.environ.get('DIGITALOCEAN_API_KEY')

    if None in (client_id, api_key):
        return None

    return DigitalOceanNodeDriver(
        key=client_id,
        secret=api_key,
    )


real_driver = driver_from_environment()

class RealListKernelsTests(make_list_kernels_tests(real_driver)):
    """
    """

if real_driver is None:
    RealListKernelsTests.skip = 'Missing DIGITALOCEAN environment variables'
