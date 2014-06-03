# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for :py:mod:`flocker.route._iptables`.
"""

from __future__ import print_function

from socket import socket

from netifaces import AF_INET, interfaces, ifaddresses
from ipaddr import IPAddress

from twisted.trial.unittest import SkipTest, TestCase
from twisted.internet import reactor

from .. import create


def connect_nonblocking(address, port):
    client = socket()
    client.setblocking(False)
    client.connect_ex((address.exploded, port))
    return client



class CreateTests(TestCase):
    """
    Tests for the creation of new external routing rules.
    """
    def setUp(self):
        self.addresses = [
            IPAddress(address['addr'])
            for name in interfaces()
            for address in ifaddresses(name).get(AF_INET, [])
        ]
        if len(self.addresses) < 2:
            raise SkipTest(
                "Cannot test proxying without at least two addresses.")

        self.serverAddress = self.addresses[0]
        self.proxyAddress = self.addresses[1]


        # This is the target of the proxy which will be created.
        self.server = socket()
        self.server.bind((self.serverAddress.exploded, 0))
        self.server.listen(1)

        # This is used to accept connections over the local network stack.
        # They should be nearly instantaneous.  If they are not then something
        # is *probably* wrong (and hopefully it isn't just an instance of the
        # machine being so loaded the local network stack can't complete a TCP
        # handshake in under one second...).
        self.server.settimeout(1)

        self.port = self.server.getsockname()[1]


    def test_setup(self):
        """
        A connection attempt to the server created in ``setUp`` is successful.
        """
        client = connect_nonblocking(self.serverAddress, self.port)
        accepted, client_address = self.server.accept()
        self.assertEqual(client.getsockname(), client_address)


    def test_connection(self):
        """
        A connection attempt is forwarded to the specified destination address.
        """
        creating = create(reactor, self.serverAddress, self.port)
        def created(ignored):
            client = connect_nonblocking(self.proxyAddress, self.port)
            accepted, client_address = self.server.accept()
            self.assertEqual(client.getsockname(), client_address)
        creating.addCallback(created)
        return creating
