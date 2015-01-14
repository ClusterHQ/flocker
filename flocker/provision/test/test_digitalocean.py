# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for ``flocker.provision._digitalocean``.
"""

import os

from twisted.trial.unittest import SynchronousTestCase

from flocker.provision._digitalocean import DigitalOceanNodeDriverV2


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

    def request(self, action, method='GET'):
        return CannedResponse(self._response)


class ListKernelsTestsMixin(object):
    """
    Tests for ``DigitalOceanNodeDriverV2.list_kernels``.
    """
    def test_success(self):
        """
        ``DigitalOceanNodeDriverV2.list_kernels`` returns a ``list`` of
        ``DigitalOceanKernel`` instances for the supplied ``droplet_id``.
        """
        actual_kernels = self.driver.list_kernels(droplet_id='2800208')
        expected_kernels = []
        self.assertEqual(expected_kernels, actual_kernels)


def make_tests(driver, tests_mixin):
    class Tests(tests_mixin, SynchronousTestCase):
        def setUp(self):
            self.driver = driver
    return Tests


canned_connection = CannedResponseConnection(
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


class CannedListKernelsTests(
        make_tests(
            DigitalOceanNodeDriverV2(token=object(),
                                     connection=canned_connection),
            ListKernelsTestsMixin)
):
    """
    """


def driver_from_environment():
    """
    """
    token = os.environ.get('DIGITALOCEAN_TOKEN')
    if None in (token,):
        return None

    return DigitalOceanNodeDriverV2(token=token)


real_driver = driver_from_environment()

class RealListKernelsTests(make_tests(real_driver, ListKernelsTestsMixin)):
    """
    """

if real_driver is None:
    RealListKernelsTests.skip = 'Missing DIGITALOCEAN environment variables'
