# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for :py:mod:`flocker.route._iptables`.
"""

from __future__ import print_function

from os import getuid
from socket import socket

from netifaces import AF_INET, interfaces, ifaddresses
from ipaddr import IPAddress

from twisted.trial.unittest import SkipTest, TestCase

from .. import create


def connect_nonblocking(ip, port):
    """
    Attempt a TCP connection to the given address without blocking.
    """
    client = socket()
    client.setblocking(False)
    client.connect_ex((ip.exploded, port))
    return client



def testEnvironmentConfigured():
    """
    Determine whether it is possible to exercise the proxy setup functionality
    in the current execution environment.

    :return: :obj:`True` if the proxy setup functionality could work given the
        underlying system and the privileges of this process, :obj:`False`
        otherwise.
    """
    # TODO: A nicer approach would be to create a new network namespace,
    # configure a couple interfaces with a couple addresses in it, and run the
    # test in the context of that network namespace.
    #
    # Something like:
    #
    #    ip netns create flocker-testing
    #    ip link add veth0 type veth peer name veth1
    #    ip link set veth1 netns flocker-testing
    #    ip netns exec flocker-testing ip link set dev veth1 up
    #    ip netns exec flocker-testing ip address add 10.0.0.1/24 dev veth1
    #    ip netns exec flocker-testing ip link set dev lo up
    #
    # Or, require such to be configured already.  That setup requires
    # privileged capabilities (probably CAP_SYS_ADMIN?) though.
    #
    # The functionality under test probably also requires privileged
    # capabilities (at least CAP_NET_ADMIN I think?) though.
    #
    # So for now just require root and crap on the host system. :/
    #
    # You might want to run these tests in a container! ;)
    #
    # -exarkun
    return getuid() == 0


class CreateTests(TestCase):
    """
    Tests for the creation of new external routing rules.
    """
    def setUp(self):
        """
        Select some addresses between which to proxy and set up a server to act
        as the target of the proxying.
        """
        if not testEnvironmentConfigured():
            raise SkipTest(
                "Cannot test port forwarding without suitable test environment.")

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
        creating = create(self.serverAddress, self.port)
        def created(ignored):
            client = connect_nonblocking(self.proxyAddress, self.port)
            accepted, client_address = self.server.accept()
            self.assertEqual(client.getsockname(), client_address)
        creating.addCallback(created)
        return creating
