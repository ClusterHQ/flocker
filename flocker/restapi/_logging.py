# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
This module defines the Eliot log events emitted by the API implementation.
"""

__all__  = [
    "REQUEST_PATH",

    "REQUEST",
    ]

from eliot import Field, ActionType

LOG_SYSTEM = u"api"

REQUEST_PATH = Field.forTypes(
    u"request_path", [unicode],
    u"The absolute path of the resource to which the request was issued.")

REQUEST = ActionType(
    LOG_SYSTEM,
    [REQUEST_PATH],
    [],
    u"A request was received on the public HTTP interface.")
