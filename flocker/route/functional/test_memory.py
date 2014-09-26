# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Functional tests for :py:mod:`flocker.route._memory`.
"""

from .. import make_memory_network
from .networktests import make_proxying_tests


class MemoryProxyInterfaceTests(make_proxying_tests(make_memory_network)):
    """
    Apply the generic ``INetwork`` test suite to the in-memory only
    implementation.
    """
