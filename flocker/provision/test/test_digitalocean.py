# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for ``flocker.provision._digitalocean``.
"""
import httplib
import os
import json
import re

from characteristic import Attribute, attributes

from twisted.trial.unittest import SynchronousTestCase, FailTest

from libcloud.common.base import JsonResponse

from flocker.provision._digitalocean import DigitalOceanNodeDriverV2


# It would be nice to use libcloud.common.base.JsonResponse instead of defining
# our own response type here.  However, JsonResponse is not very amenable to
# testing.  It wants an HTTPResponse object and it wants to read stuff from
# that object in order to initialize itself.  With this CannedResponse we can
# just pass in some structured data representing the case we want to test.
class CannedResponse(object):
    def __init__(self, expected_response):
        self.object = expected_response


class CannedError(CannedResponse, Exception):
    """
    """


class FakeHTTPLibResponse(object):
    reason = ''

    def __init__(self, body, status):
        self.body = body
        self.status = status

    def getheaders(self):
        return []

    def read(self):
        return self.body


def canned_json_response(response_object, response_status=httplib.OK):
    """
    """
    def response():
        response_content = json.dumps(response_object)
        return JsonResponse(
            response=FakeHTTPLibResponse(body=response_content, status=response_status),
            connection=object()
        )
    return response


def canned_json_error(response_object, response_status=httplib.NOT_FOUND):
    return canned_json_response(response_object, response_status)


@attributes([
    'path',
    Attribute('method', default_value='GET'),
    Attribute('data', default_value=b''),
], apply_immutable=True)
class RequestKey(object):
    """
    """

def request_key(*args):
    kwargs = dict(zip(('path', 'method', 'data'), args))
    return RequestKey(**kwargs)


class CannedResponseConnection(object):
    """
    """
    def __init__(self, expected_responses):
        self._responses = expected_responses

    def request(self, action, method='GET', data=b''):
        for key in self._responses:
            if key.method != method:
                continue
            match = re.match(key.path, action)
            if match is None:
                continue
            response = self._responses[key]
            return response()
        else:
            raise FailTest(
                'Unexpected request. '
                'Action: {}, Method: {}, Expected: {}'.format(
                    action, method, self._responses.keys())
            )


class ListKernelsTestsMixin(object):
    """
    Tests for ``DigitalOceanNodeDriverV2.list_kernels``.
    """
    def test_kernel_dict(self):
        """
        ``DigitalOceanNodeDriverV2.list_kernels`` returns a ``list`` of
        ``dict``s containing information about the kernels available for the
        supplied ``droplet_id``.

        A more specific dictionary format test is included in the canned driver
        test below.
        """
        actual_kernels = self.driver.list_kernels(droplet_id=self.droplet_id)
        expected_keys = set(['id', 'name', 'version'])
        self.assertEqual(expected_keys, set(actual_kernels[0].keys()))

    def test_unknown_droplet_id(self):
        """
        ``DigitalOceanNodeDriverV2.list_kernels``
        ``DigitalOceanKernel`` instances for the supplied ``droplet_id``.
        """
        exception = self.assertRaises(
            Exception,
            self.driver.list_kernels,
            droplet_id=''
        )
        self.assertEqual(
            {
                u'message': (u'The resource you were accessing '
                             u'could not be found.'),
                u'id': u'not_found'
            },
            exception.args[0]
        )


def make_tests(driver, tests_mixin):
    class Tests(tests_mixin, SynchronousTestCase):
        def setUp(self):
            self.driver = driver
    return Tests


# From https://developers.digitalocean.com/#list-all-available-kernels-for-a-droplet
JSON_KERNEL = {
  "id": 231,
  "name": "DO-recovery-static-fsck",
  "version": "3.8.0-25-generic"
}

JSON_KERNELS = {
    "kernels": [JSON_KERNEL],
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

JSON_NOT_FOUND = {
    "id": "not_found",
    "message": "The resource you were accessing could not be found."
}

class CannedListKernelsTests(
        make_tests(
            DigitalOceanNodeDriverV2(
                token=object(),
                connection=CannedResponseConnection(
                    expected_responses = {
                        request_key('/droplets/\d+/kernels'): canned_json_response(JSON_KERNELS),
                        request_key('/droplets//kernels'): canned_json_error(JSON_NOT_FOUND)
                    }
                )
            ),
            ListKernelsTestsMixin
        )
):

    """
    """
    droplet_id = '12345'
    def test_success(self):
        """
        ``DigitalOceanNodeDriverV2.list_kernels`` returns a ``list`` of
        ``dict``s for the supplied ``droplet_id``.
        """
        actual_kernels = self.driver.list_kernels(droplet_id=self.droplet_id)
        expected_kernels = [JSON_KERNEL]
        self.assertEqual(expected_kernels, actual_kernels)


def driver_from_environment():
    """
    """
    token = os.environ.get('DIGITALOCEAN_TOKEN')
    if None in (token,):
        return None

    return DigitalOceanNodeDriverV2(token=token)


def live_api_tests_from_environment(tests_mixin):
    real_driver = driver_from_environment()
    class Tests(make_tests(real_driver, tests_mixin)):
        pass
    if real_driver is None:
        Tests.skip = 'Missing DIGITALOCEAN environment variables'
    return Tests


class RealListKernelsTests(
        live_api_tests_from_environment(ListKernelsTestsMixin)):
    """
    """
    droplet_id = os.environ.get('DIGITALOCEAN_DROPLET_ID')


# https://developers.digitalocean.com/#change-the-kernel
JSON_CHANGE_KERNEL_ACTION = {
    "id": 36804951,
    "status": "in-progress",
    "type": "change_kernel",
    "started_at": "2014-11-14T16:34:20Z",
    "completed_at": None,
    "resource_id": 3164450,
    "resource_type": "droplet",
    "region": "nyc3"
}

JSON_CHANGE_KERNEL_RESPONSE = {
    "action": JSON_CHANGE_KERNEL_ACTION
}


class ChangeKernelTestsMixin(object):
    def test_success(self):
        """
        ``DigitalOceanNodeDriverV2.change_kernel`` returns
        ``dict`` of information about the ``action``.
        """
        self.assertEqual(
            JSON_CHANGE_KERNEL_ACTION,
            self.driver.change_kernel(
                droplet_id=self.droplet_id,
                kernel_id=self.kernel_id
            )
        )


class CannedChangeKernelTests(
    make_tests(
        DigitalOceanNodeDriverV2(
            token=object(),
            connection=CannedResponseConnection(
                expected_responses = {
                    request_key('/droplets/\d+/actions', 'POST'): canned_json_response(JSON_CHANGE_KERNEL_RESPONSE),
                    request_key('/droplets//actions'): canned_json_error(JSON_NOT_FOUND)
                }
            )
        ),
        ChangeKernelTestsMixin
    )
):
    """
    """
    droplet_id = 12345
    kernel_id = 12345
