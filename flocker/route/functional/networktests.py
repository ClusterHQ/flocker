# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Generic tests for ``flocker.route.INetwork`` implementations.
"""

from zope.interface.verify import verifyObject
from ipaddr import IPAddress
from twisted.trial.unittest import SynchronousTestCase

from .. import INetwork


def make_proxying_tests(make_network):
    """
    Define the tests common to all ``INetwork`` implementations.

    :param make_network: A no-argument callable which returns the ``INetwork``
        provider to test.

    :return: A ``TestCase`` subclass which defines a number of
        ``INetwork``-related tests.
    """
    class ProxyingTests(SynchronousTestCase):
        """
        Tests for the self-consistency of the behavior of an ``INetwork``
        implementation.
        """
        def setUp(self):
            self.network = make_network()

        def test_interface(self):
            """
            The object implements ``INetwork``.
            """
            self.assertTrue(verifyObject(INetwork, self.network))

        def test_proxy_object(self):
            """
            The :py:meth:`INetwork.create_proxy_to` implementation returns an
            object with attributes describing the created proxy.
            """
            server_ip = IPAddress("10.2.3.4")
            port = 54321
            proxy = self.network.create_proxy_to(server_ip, port)
            self.assertEqual((proxy.ip, proxy.port), (server_ip, port))

        def test_empty(self):
            """
            The :py:meth:`INetwork.enumerate_proxies` implementation returns an
            empty :py:class:`list` when no proxies have been created.
            """
            self.assertEqual([], self.network.enumerate_proxies())

        def test_a_proxy(self):
            """
            After :py:meth:`INetwork.create_proxy_to` is used to create a
            proxy, :py:meth:`INetwork.enumerate_proxies` returns a
            :py:class:`list` including an object describing that proxy.
            """
            ip = IPAddress("10.1.2.3")
            port = 4567
            proxy = self.network.create_proxy_to(ip, port)
            self.assertEqual([proxy], self.network.enumerate_proxies())

        def test_some_proxies(self):
            """
            After :py:meth:`INetwork.route.create_proxy_to` is used to create
            several proxies, :py:meth:`INetwork.enumerate_proxies` returns a
            :py:class:`list` including an object for each of those proxies.
            """
            ip = IPAddress("10.1.2.3")
            port = 4567
            proxy_one = self.network.create_proxy_to(ip, port)
            proxy_two = self.network.create_proxy_to(ip, port + 1)

            self.assertEqual(
                sorted([proxy_one, proxy_two]),
                sorted(self.network.enumerate_proxies()))

        def test_deleted_proxies_not_enumerated(self):
            """
            Once a proxy has been deleted,
            :py:meth:`INetwork.enumerate_proxies` does not include an element
            in the sequence it returns corresponding to it.
            """
            proxy = self.network.create_proxy_to(IPAddress("10.2.3.4"), 4321)
            self.network.delete_proxy(proxy)
            self.assertEqual([], self.network.enumerate_proxies())

        def test_only_specified_proxy_deleted(self):
            proxy_one = self.network.create_proxy_to(IPAddress("10.0.0.1"), 1)
            proxy_two = self.network.create_proxy_to(IPAddress("10.0.0.2"), 2)
            self.network.delete_proxy(proxy_one)
            self.assertEqual([proxy_two], self.network.enumerate_proxies())

    return ProxyingTests
