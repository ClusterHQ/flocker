# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Generic tests for ``flocker.route.INetwork`` implementations.
"""

from zope.interface.verify import verifyObject
from ipaddr import IPAddress

from ...testtools import TestCase
from .. import INetwork, OpenPort


def make_network_tests(make_network):
    """
    Define the tests common to all ``INetwork`` implementations.

    :param make_network: A no-argument callable which returns the ``INetwork``
        provider to test.

    :return: A ``TestCase`` subclass which defines a number of
        ``INetwork``-related tests.
    """
    class NetworkTests(TestCase):
        """
        Tests for the self-consistency of the behavior of an ``INetwork``
        implementation.
        """
        def setUp(self):
            super(NetworkTests, self).setUp()
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

        def test_empty_proxies(self):
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
                set([proxy_one, proxy_two]),
                set(self.network.enumerate_proxies()))

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
            """
            Proxies other than a deleted proxy are still listed.
            """
            proxy_one = self.network.create_proxy_to(IPAddress("10.0.0.1"), 1)
            proxy_two = self.network.create_proxy_to(IPAddress("10.0.0.2"), 2)
            self.network.delete_proxy(proxy_one)
            self.assertEqual([proxy_two], self.network.enumerate_proxies())

        def test_port_object(self):
            """
            The :py:meth:`INetwork.open_port` implementation returns an
            object with attributes describing the created proxy.
            """
            port = 54321
            open_port = self.network.open_port(port)
            self.assertEqual(open_port, OpenPort(port=port))

        def test_empty_open_ports(self):
            """
            The :py:meth:`INetwork.enumerate_open_ports` implementation returns
            an empty :py:class:`list` when no ports have been opened.
            """
            self.assertEqual([], self.network.enumerate_open_ports())

        def test_an_open_port(self):
            """
            After :py:meth:`INetwork.open_port` is used to open a
            port, :py:meth:`INetwork.enumerate_open_ports` returns a
            :py:class:`list` including an object describing that open port.
            """
            port = 4567
            open_port = self.network.open_port(port)
            self.assertEqual([open_port], self.network.enumerate_open_ports())

        def test_some_open_ports(self):
            """
            After :py:meth:`INetwork.route.open_port` is used to create
            several open ports, :py:meth:`INetwork.enumerate_open_port` returns
            a :py:class:`list` including an object for each of those open
            ports.
            """
            port = 4567
            open_port_one = self.network.open_port(port)
            open_port_two = self.network.open_port(port + 1)

            self.assertEqual(
                set([open_port_one, open_port_two]),
                set(self.network.enumerate_open_ports()))

        def test_deleted_open_ports_not_enumerated(self):
            """
            Once an open port has been deleted,
            :py:meth:`INetwork.enumerate_open_ports` does not include an
            element in the sequence it returns corresponding to it.
            """
            open_port = self.network.open_port(4321)
            self.network.delete_open_port(open_port)
            self.assertEqual([], self.network.enumerate_open_ports())

        def test_only_specified_open_port_deleted(self):
            """
            Open ports other than a deleted port are still listed.
            """
            open_port_one = self.network.open_port(1)
            open_port_two = self.network.open_port(2)
            self.network.delete_open_port(open_port_one)
            self.assertEqual(
                [open_port_two],
                self.network.enumerate_open_ports())

    return NetworkTests
