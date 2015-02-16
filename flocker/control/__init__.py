# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

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
    applications_to_flocker_yaml, model_from_configuration,
    current_from_configuration,
    )
from ._model import (
    Application, Deployment, DockerImage, Node, Port, Link, AttachedVolume,
    NodeState, Manifestation, Dataset,
    )

__all__ = [
    'FlockerConfiguration',
    'ConfigurationError',
    'applications_to_flocker_yaml',
    'current_from_configuration',
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
    'Manifestation',
    'Dataset',
]
