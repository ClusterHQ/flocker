# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
This module defines the Eliot log events emitted by the API implementation.
"""

__all__ = [
    "JSON_REQUEST",
    "REQUEST",
    ]

from eliot import Field, ActionType

LOG_SYSTEM = u"api"

METHOD = Field.forTypes(
    u"method", [unicode, bytes], u"The HTTP method of the request.")
REQUEST_PATH = Field.forTypes(
    u"request_path", [unicode, bytes],
    u"The absolute path of the resource to which the request was issued.")
JSON = Field.forTypes(
    u"json", [unicode, bytes, dict, list, None, bool, float],
    u"JSON, either request or response depending on context.")
RESPONSE_CODE = Field.forTypes(
    u"code", [int],
    u"The response code for the request.")


REQUEST = ActionType(
    LOG_SYSTEM + u":request",
    [REQUEST_PATH, METHOD],
    [],
    u"A request was received on the public HTTP interface.")
JSON_REQUEST = ActionType(
    LOG_SYSTEM + u":json_request",
    [JSON],
    [RESPONSE_CODE, JSON],
    u"A request containing JSON request and response.")
