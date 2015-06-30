# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Shared flocker components.
"""

__all__ = [
    'INode', 'FakeNode', 'ProcessNode', 'gather_deferreds',
    'auto_threaded', 'auto_openstack_logging',
    'get_all_ips', 'ipaddress_from_string',
]

import platform

from ._ipc import INode, FakeNode, ProcessNode
from ._defer import gather_deferreds
from ._thread import auto_threaded
from ._net import get_all_ips, ipaddress_from_string

if platform.system() == 'Linux':
    # For some reason I don't understand,  keystoneclient has problems on OS X.
    # Fortunately, we don't need keystoneclient on OS X.
    from ._openstack import auto_openstack_logging
