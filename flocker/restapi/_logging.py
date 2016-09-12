# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
This module defines the Eliot log events emitted by the API implementation.
"""

from eliot import Field, ActionType

__all__ = [
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
    u"The JSON request body.")
RESPONSE_CODE = Field.forTypes(
    u"code", [int],
    u"The response code for the request.")


# It would be nice if RESPONSE_CODE was in REQUEST; see FLOC-1586.
REQUEST = ActionType(
    LOG_SYSTEM + u":request",
    [REQUEST_PATH, METHOD],
    [],
    u"A request was received on the public HTTP interface.")
