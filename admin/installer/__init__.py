# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Installer scripts and modules which should not be shipped with Flocker.
"""

from ._limits import (
    MIN_CLUSTER_SIZE,
    MAX_CLUSTER_SIZE
)

__all__ = [
    MIN_CLUSTER_SIZE, MAX_CLUSTER_SIZE
]
