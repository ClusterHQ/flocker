# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Infrastructure for publishing a REST HTTP API.
"""

from ._infrastructure import (
    structured, EndpointResponse, user_documentation, private_api,
    )

from ._error import makeBadRequest as make_bad_request


__all__ = [
    "structured", "EndpointResponse", "user_documentation",
    "make_bad_request", "private_api",
]
