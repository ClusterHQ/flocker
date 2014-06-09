# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for :py:mod:`flocker.route._iptables`.
"""

from __future__ import print_function

from errno import ECONNREFUSED
from os import getuid, getpid
from socket import error, socket
from unittest import skipUnless
from subprocess import check_output

from netifaces import AF_INET, interfaces, ifaddresses
from ipaddr import IPAddress, IPNetwork

from twisted.trial.unittest import SkipTest, TestCase

from .. import create

ADDRESSES = [
    IPAddress(address['addr'])
    for name in interfaces()
    for address in ifaddresses(name).get(AF_INET, [])
]


def connect_nonblocking(ip, port):
    """
    Attempt a TCP connection to the given address without blocking.
    """
    client = socket()
    client.setblocking(False)
    client.connect_ex((ip.exploded, port))
    return client


def is_environment_configured():
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
    @skipUnless(
        is_environment_configured(),
        "Cannot test port forwarding without suitable test environment.")
    @skipUnless(
        len(ADDRESSES) >= 2,
        "Cannot test proxying without at least two addresses.")
    def setUp(self):
        """
        Select some addresses between which to proxy and set up a server to act
        as the target of the proxying.
        """
        self.server_ip = ADDRESSES[0]
        self.proxy_ip = ADDRESSES[1]

        # This is the target of the proxy which will be created.
        self.server = socket()
        self.server.bind((self.server_ip.exploded, 0))
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
        client = connect_nonblocking(self.server_ip, self.port)
        accepted, client_address = self.server.accept()
        self.assertEqual(client.getsockname(), client_address)

    def test_connection(self):
        """
        A connection attempt is forwarded to the specified destination address.
        """
        # Note - we're leaking iptables rules into the system here.
        # https://github.com/hybridlogic/flocker/issues/22
        create(self.server_ip, self.port)

        client = connect_nonblocking(self.proxy_ip, self.port)
        accepted, client_address = self.server.accept()
        self.assertEqual(client.getsockname(), client_address)

    def test_client_to_server(self):
        """
        A proxied connection will deliver bytes from the client side to the
        server side.
        """
        create(self.server_ip, self.port)

        client = connect_nonblocking(self.proxy_ip, self.port)
        accepted, client_address = self.server.accept()

        client.send(b"x")
        self.assertEqual(b"x", accepted.recv(1))

    def test_server_to_client(self):
        """
        A proxied connection will deliver bytes from the server side to the
        client side.
        """
        create(self.server_ip, self.port)

        client = connect_nonblocking(self.proxy_ip, self.port)
        accepted, client_address = self.server.accept()

        accepted.send(b"x")
        self.assertEqual(b"x", client.recv(1))

    def test_remote_connections_unaffected(self):
        """
        A connection attempt to an IP not assigned to this host on the proxied
        port is not proxied.
        """
        networks = {
            IPNetwork("10.0.0.0/8"),
            IPNetwork("172.16.0.0/12"),
            IPNetwork("192.168.0.0/16")}

        for address in ADDRESSES:
            for network in networks:
                if address in network:
                    networks.remove(network)
                    break
        if not networks:
            raise SkipTest("No private networks available")

        network = next(iter(networks))
        gateway = network[1]
        address = network[2]

        # The strategy taken by this test is to create a new, clean network
        # stack and then treat it like a foreign host.  A connection to that
        # foreign host should not be proxied.  This is possible because Linux
        # supports the creation of an arbitrary number of instances of its
        # network stack, all isolated from each other.
        #
        # To learn more, here are some links:
        #
        # http://man7.org/linux/man-pages/man8/ip-netns.8.html
        # http://blog.scottlowe.org/2013/09/04/introducing-linux-network-namespaces/
        #
        # Note also that Linux network namespaces are how Docker creates
        # isolated network environments.

        # Create a remote "host" that the test can reliably fail a connection
        # attempt to.
        pid = getpid()
        veth0 = b"veth_" + hex(pid)
        veth1 = b"veth1"
        network_namespace = b"%s.%s" % (self.id(), getpid())

        def run(cmd):
            check_output(cmd.split())

        # Destroy whatever system resources we go on to allocate in this test.
        # We set this up first so even if one of the operations encounters an
        # error after a resource has been allocated we'll still clean it up.
        # It's not an error to try to delete things that don't exist
        # (conveniently).
        self.addCleanup(run, b"ip netns delete " + network_namespace)
        self.addCleanup(run, b"ip link delete " + veth0)

        ops = [
            # Create a new network namespace where we can assign a non-local
            # address to use as the target of a connection attempt.
            b"ip netns add %(netns)s",

            # Create a virtual ethernet pair so there is a network link between
            # the host and the new network namespace.
            b"ip link add %(veth0)s type veth peer name %(veth1)s",

            # Assign an address to the virtual ethernet interface that will
            # remain on the host.  This will be our "gateway" into the network
            # namespace.
            b"ip address add %(gateway)s dev %(veth0)s",

            # Bring it up.
            b"ip link set dev %(veth0)s up",

            # Put the other virtual ethernet interface into the network
            # namespace.  Now it will only affect networking behavior for code
            # running in that network namespace, not for code running directly
            # on the host network (like the code in this test and whatever
            # iptables rules we created).
            b"ip link set %(veth1)s netns %(netns)s",

            # Assign to that virtual ethernet interface an address on the same
            # (private, unused) network as the address we gave to the gateway
            # interface.
            b"ip netns exec %(netns)s ip address add %(address)s "
            b"dev %(veth1)s",

            # And bring it up.
            b"ip netns exec %(netns)s ip link set dev %(veth1)s up",

            # Add a route into the network namespace via the virtual interface
            # for traffic bound for addresses on that network.
            b"ip route add %(network)s dev %(veth0)s scope link",

            # And add a reciprocal route so traffic generated inside the
            # network namespace (like TCP RST packets) can get back to us.
            b"ip netns exec %(netns)s ip route add default dev %(veth1)s",
        ]

        params = dict(
            netns=network_namespace, veth0=veth0, veth1=veth1,
            address=address, gateway=gateway, network=network,
            )
        for op in ops:
            run(op % params)

        # Create the proxy which we expect not to be invoked.
        create(self.server_ip, self.port)

        client = socket()
        client.settimeout(1)

        # Try to connect to an address hosted inside that network namespace.
        # It should fail.  It should not be proxied to the server created in
        # setUp.
        exception = self.assertRaises(
            error, client.connect, (str(address), self.port))
        self.assertEqual(ECONNREFUSED, exception.errno)
