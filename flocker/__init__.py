# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Flocker is a hypervisor that provides ZFS-based replication and fail-over
functionality to a Linux-based user-space operating system.
"""

from ._version import get_versions
__version__ = get_versions()['version']
del get_versions
