# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Control service for managing a Flocker cluster.

A Flocker cluster is composed of a number of nodes. The control service is
in charge of managing the desired configuration and exposes a public API
for modifying and retrieving the desired configuration. The nodes are
modified by convergence agents that retrieve the desired configuration
from the control service and make necessary changes to the nodes so that
they match that configuration.
"""

from ._config import (
    FlockerConfiguration, ConfigurationError, FigConfiguration,
    model_from_configuration,
)
from ._model import (
    IClusterStateChange, Application, Deployment, DockerImage, Node, Port,
    Link, AttachedVolume, NodeState, Manifestation, Dataset, RestartNever,
    RestartOnFailure, RestartAlways, DeploymentState, NonManifestDatasets,
    same_node, IClusterStateWipe, Leases, Lease, LeaseError, pmap_field,
    ChangeSource, UpdateNodeStateEra, NoWipe,
)
from ._protocol import (
    IConvergenceAgent,
    NodeStateCommand,
    AgentAMP,
    SetNodeEraCommand,
)

__all__ = [
    'same_node',
    'IClusterStateChange',
    'IClusterStateWipe',
    'FlockerConfiguration',
    'ConfigurationError',
    'model_from_configuration',
    'Application',
    'Deployment',
    'DockerImage',
    'FigConfiguration',
    'Node',
    'Port',
    'Link',
    'AttachedVolume',
    'NodeState',
    'DeploymentState',
    'Manifestation',
    'Dataset',
    'RestartNever',
    'RestartOnFailure',
    'RestartAlways',
    'NonManifestDatasets',

    'IConvergenceAgent',
    'NodeStateCommand',
    'SetNodeEraCommand',
    'AgentAMP',
    'pmap_field',
    'Lease',
    'Leases',
    'LeaseError',
    'ChangeSource',
    'UpdateNodeStateEra',
    'NoWipe',
]
