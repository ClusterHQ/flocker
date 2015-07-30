# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Client for the Flocker REST API.

This may eventually be a standalone package.
"""

from ._client import IFlockerAPIV1, FakeFlockerAPIV1


__all__ = ["IFlockerAPIV1", "FakeFlockerAPIV1"]
