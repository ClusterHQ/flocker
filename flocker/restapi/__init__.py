# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Infrastructure for publishing a REST HTTP API.
"""

from ._infrastructure import (
    structured, EndpointResponse, userDocumentation,
    )


__all__ = ["structured", "EndpointResponse", "userDocumentation"]
