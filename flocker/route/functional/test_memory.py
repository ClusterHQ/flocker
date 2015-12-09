# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Functional tests for :py:mod:`flocker.route._memory`.
"""

from .. import make_memory_network
from .networktests import make_network_tests


class MemoryNetworkInterfaceTests(make_network_tests(make_memory_network)):
    """
    Apply the generic ``INetwork`` test suite to the in-memory only
    implementation.
    """
