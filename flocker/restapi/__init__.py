# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Infrastructure for publishing a REST HTTP API.
"""

from ._infrastructure import (
    structured, EndpointResponse, user_documentation,
    )


__all__ = ["structured", "EndpointResponse", "user_documentation"]
