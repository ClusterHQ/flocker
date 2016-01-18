# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
This module defines the Eliot log events emitted by the API implementation.
"""

from eliot import Field, ActionType

__all__ = [
    "JSON_REQUEST",
    "REQUEST",
    ]

LOG_SYSTEM = u"api"

METHOD = Field(u"method", lambda method: method,
               u"The HTTP method of the request.")
REQUEST_PATH = Field(
    u"request_path", lambda path: path,
    u"The absolute path of the resource to which the request was issued.")
JSON = Field.forTypes(
    u"json", [unicode, bytes, dict, list, None, bool, float],
    u"JSON, either request or response depending on context.")
RESPONSE_CODE = Field.forTypes(
    u"code", [int],
    u"The response code for the request.")


# It would be nice if RESPONSE_CODE was in REQUEST instead of
# JSON_REQUEST; see FLOC-1586.
REQUEST = ActionType(
    LOG_SYSTEM + u":request",
    [REQUEST_PATH, METHOD],
    [],
    u"A request was received on the public HTTP interface.")
JSON_REQUEST = ActionType(
    LOG_SYSTEM + u":json_request",
    [JSON],
    [RESPONSE_CODE, JSON],
    u"A request containing JSON request and response bodies.")
