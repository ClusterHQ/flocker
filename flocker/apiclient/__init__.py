# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Client for the Flocker REST API.

This may eventually be a standalone package.
"""

from ._client import (
    IFlockerAPIV1Client, FakeFlockerClient, Dataset, DatasetState,
    DatasetAlreadyExists, FlockerClient, Lease, LeaseAlreadyHeld,
    conditional_create, DatasetsConfiguration, Node, MountedDataset,
)

__all__ = ["IFlockerAPIV1Client", "FakeFlockerClient", "Dataset",
           "DatasetState", "DatasetAlreadyExists", "FlockerClient",
           "Lease", "LeaseAlreadyHeld", "conditional_create",
           "DatasetsConfiguration", "Node", "MountedDataset", ]
