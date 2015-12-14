# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Shared flocker components.

:var bitmath.GiB RACKSPACE_MINIMUM_VOLUME_SIZE: The minimum size allowed for a
    Cinder volume on Rackspace Public Cloud.
:var bitmath.GiB DEVICEMAPPER_LOOPBACK_SIZE: The default size of the loopback
    device used by the Docker devicemapper storage driver.
"""

__all__ = [
    'INode', 'FakeNode', 'ProcessNode', 'gather_deferreds',
    'auto_threaded', 'interface_decorator', 'provides',
    'get_all_ips', 'ipaddress_from_string',
    'loop_until', 'timeout', 'retry_failure', 'poll_until',
    'retry_effect_with_timeout',

    'RACKSPACE_MINIMUM_VOLUME_SIZE',
    'DEVICEMAPPER_LOOPBACK_SIZE',
]

from bitmath import GiB as _GiB

from ._ipc import INode, FakeNode, ProcessNode
from ._defer import gather_deferreds
from ._thread import auto_threaded
from ._interface import interface_decorator, provides
from ._net import get_all_ips, ipaddress_from_string
from ._retry import (
    loop_until, timeout, poll_until, retry_failure, retry_effect_with_timeout,
)

# This is currently set to the minimum size for a SATA based Rackspace Cloud
# Block Storage volume. See:
# * http://www.rackspace.com/knowledge_center/product-faq/cloud-block-storage
RACKSPACE_MINIMUM_VOLUME_SIZE = _GiB(75)

DEVICEMAPPER_LOOPBACK_SIZE = _GiB(100)
