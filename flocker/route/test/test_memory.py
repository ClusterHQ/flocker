# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Unit tests for :py:mod:`flocker.route._memory`.
"""

from ipaddr import IPAddress

from twisted.trial.unittest import SynchronousTestCase

from .. import make_memory_network


class MemoryProxyTests(SynchronousTestCase):
    """
    Tests for distinctive behaviors of the ``INetwork`` provider created by
    ``make_memory_network``.
    """
    def test_custom_used_ports(self):
        """
        Additional used ports can be specified by passing them to
        ``make_memory_network``.
        """
        extra = 20001
        ports = frozenset({50, 100, 15000})
        network = make_memory_network(used_ports=ports)
        network.create_proxy_to(IPAddress("10.0.0.1"), extra)
        expected = frozenset(ports | {extra})
        self.assertEqual(expected, network.enumerate_used_ports())
