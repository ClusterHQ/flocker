# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Unit tests for :py:mod:`flocker.route._memory`.
"""

from ipaddr import IPAddress

from twisted.trial.unittest import SynchronousTestCase

from .. import make_memory_network, Proxy


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

    def test_default_namespace(self):
        """
        ``enumerate_proxies`` returns proxies with a default namespace.
        """
        ip = IPAddress("10.2.3.4")
        port = 4321
        namespace = u"default_memory_namespace"
        network = make_memory_network()
        network.create_proxy_to(ip, 4321)
        expected = Proxy(ip=ip, port=port, namespace=namespace)
        self.assertEqual([expected], network.enumerate_proxies())
