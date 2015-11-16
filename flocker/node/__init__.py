# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

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
    P2PManifestationDeployer,
    ApplicationNodeDeployer,
)

from .script import BackendDescription, DeployerType


__all__ = [
    'IDeployer', 'ILocalState', 'NodeLocalState', 'IStateChange',
    'NoOp',
    'P2PManifestationDeployer',
    'ApplicationNodeDeployer',
    'run_state_change', 'in_parallel', 'sequentially',
    'BackendDescription', 'DeployerType',
]
