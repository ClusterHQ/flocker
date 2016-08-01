# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Persistence of cluster configuration to consul.
"""
import base64

from eliot import ActionType, Field
from eliot.twisted import DeferredContext
from treq import json_content, content
import treq
from twisted.web.http import (
    OK, NOT_FOUND
)
from zope.interface import implementer

from ._persistence import IConfigurationStore


BASE_URL = b"http://localhost:8500/v1/kv"
CONFIG_PATH = b"/com.clusterhq/flocker/current_configuration"

_LOG_HTTP_REQUEST = ActionType(
    "flocker:control:consul",
    [Field.forTypes("url", [bytes, unicode], "Request URL."),
     Field.forTypes("method", [bytes, unicode], "Request method."),
     Field("request_body", lambda o: o, "Request JSON body.")],
    [Field.forTypes("response_code", [int], "Response code."),
     Field("response_body", lambda o: o, "JSON response body.")],
    "A HTTP request.")


class ResponseError(Exception):
    """
    An unexpected response from the REST API.
    """
    def __init__(self, code, body):
        Exception.__init__(self, "Unexpected response code {}:\n{}\n".format(
            code, body))
        self.code = code


class NotFound(Exception):
    """
    Result was not found.
    """


@implementer(IConfigurationStore)
class ConsulConfigurationStore(object):
    _base_url = BASE_URL
    _treq = treq

    def _request_with_headers(
            self, method, path, body, success_codes, error_codes=None):
        """
        Send a HTTP request to the Flocker API, return decoded JSON body and
        headers.

        :param bytes method: HTTP method, e.g. PUT.
        :param bytes path: Path to add to base URL.
        :param body: If not ``None``, JSON encode this and send as the
            body of the request.
        :param set success_codes: Expected success response codes.
        :param error_codes: Mapping from HTTP response code to exception to be
            raised if it is present, or ``None`` to set no errors.
        :return: ``Deferred`` firing a tuple of (decoded JSON,
            response headers).
        """
        url = self._base_url + path
        action = _LOG_HTTP_REQUEST(url=url, method=method, request_body=body)

        if error_codes is None:
            error_codes = {}

        def error(body, code):
            if code in error_codes:
                raise error_codes[code](body)
            raise ResponseError(code, body)

        def got_response(response):
            if response.code in success_codes:
                action.addSuccessFields(response_code=response.code)
                d = json_content(response)
                d.addCallback(lambda decoded_body:
                              (decoded_body, response.headers))
                return d
            else:
                d = content(response)
                d.addCallback(error, response.code)
                return d
        headers = {}
        data = None
        if body is not None:
            headers["content-type"] = b"application/json"
            data = body

        with action.context():
            request = DeferredContext(self._treq.request(
                method, url, data=data, headers=headers,
                persistent=False,
            ))
        request.addCallback(got_response)

        def got_body(result):
            action.addSuccessFields(response_body=result[0])
            return result
        request.addCallback(got_body)
        request.addActionFinish()
        return request.result

    def _request(self, *args, **kwargs):
        """
        Send a HTTP request to the Flocker API, return decoded JSON body.

        Takes the same arguments as ``_request_with_headers``.

        :return: ``Deferred`` firing with decoded JSON.
        """
        return self._request_with_headers(*args, **kwargs).addCallback(
            lambda t: t[0])

    def initialize(self):
        """
        """
        d = self.get_content()

        def set_if_missing(failure):
            failure.trap(NotFound)
            return self.set_content(b"")
        d.addErrback(set_if_missing)
        return d

    def get_content(self):
        d = self._request(
            b"GET",
            CONFIG_PATH,
            None,
            {OK},
            error_codes={NOT_FOUND: NotFound}
        )

        def decode(result):
            value = result[0]['Value']
            if value is None:
                return b""
            else:
                return base64.decodestring(value)

        d.addCallback(decode)
        return d

    def set_content(self, content_bytes):
        return self._request(
            b"PUT",
            CONFIG_PATH,
            content_bytes,
            success_codes={OK},
        )
