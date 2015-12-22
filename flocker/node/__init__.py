# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Local node manager for Flocker.
"""

from ._change import (
    IStateChange, in_parallel, sequentially, run_state_change, NoOp,
)

from ._deploy import (
    IDeployer,
    ILocalState,
    NodeLocalState,
)
from ._container import ApplicationNodeDeployer
from ._p2p import P2PManifestationDeployer

from .script import BackendDescription, DeployerType

from ._docker import dockerpy_client


__all__ = [
    'IDeployer', 'ILocalState', 'NodeLocalState', 'IStateChange',
    'NoOp',
    'P2PManifestationDeployer',
    'ApplicationNodeDeployer',
    'run_state_change', 'in_parallel', 'sequentially',
    'BackendDescription', 'DeployerType',

    'dockerpy_client',
]
