# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
# -*- test-case-name: flocker.route.test_create -*-

"""
Manipulate network routing behavior on a node using ``iptables``.
"""

from __future__ import unicode_literals

from os import environ

from twisted.internet.defer import Deferred, gatherResults
from twisted.internet.protocol import Protocol
from twisted.internet.endpoints import ProcessEndpoint, connectProtocol



class Collector(Protocol):
    def __init__(self, result):
        self.result = result


    def connectionMade(self):
        self.data = []


    def dataReceived(self, data):
        self.data.append(data)


    def connectionLost(self, reason):
        self.result.callback((self.data, reason))



def create(reactor, ip, port):
    """
    Create a new TCP proxy to `ip` on port `port`.

    :param ip: The destination to which to proxy.
    :type ip: ipaddr.IPAddress

    :param port: The TCP port number on which to proxy.
    :type port: int
    """
    # We don't want to mangle traffic coming *out* of the target container.
    # That container might be on this host or it might be somewhere else.  So
    # we might need to figure that out (or accept it as an argument) and add a
    # "not interface foo" filter here.

    # The first goal is to configure "Destination NAT" (DNAT).  We're just
    # going to rewrite the destination address of traffic arriving on the
    # specified port so it looks like it is destined for the specified ip
    # instead of destined for "us".  This gets the packets delivered to the
    # right destination.
    prerouting = [
        b"iptables",

        # All NAT stuff happens in the netfilter NAT table.
        b"-t", b"nat",

        # Append this rule to the PREROUTING table.  Destination NAT has to
        # happen "pre"-routing so that the normal routing rules on the machine
        # will use the re-written destination address and get the packet to
        # that new destination.
        b"-A", b"PREROUTING",

        # Only re-route traffic with a destination port matching the one we
        # were told to manipulate.  It is also necessary to specify TCP (or
        # UDP) here since that is the layer of the network stack that defines
        # ports.
        b"--protocol", b"tcp",
        b"--dport", unicode(port).encode("ascii"),

        # If the filter matched, jump to the DNAT chain to handle doing the
        # actual packet mangling.  DNAT is a built-in chain that already knows
        # how to do this.
        b"-j", b"DNAT",

        # Pass an argument to the DNAT chain so it knows how to mangle the
        # packet - rewrite the destination IP of the address to the target we
        # were told to use.
        b"--to-destination", unicode(ip).encode("ascii"),
    ]

    # Bonus round!  Having performed DNAT (changing the destination) during
    # prerouting we are now prepared to send the packet on somewhere else.  On
    # its way out of this system it is also necessary to further modify and
    # then track that packet.  We want it to look like it comes from us (the
    # downstream client will be *very* confused if the node we're passing the
    # packet on to replies *directly* to them; and by confused I mean it will
    # be totally broken, of course) so we also need to "masquerade" in the
    # postrouting chain.  This changes the source address of the packet to the
    # address of the external interface the packet is exiting upon.  Doing SNAT
    # here would be a little bit more efficient because the kernel could avoid
    # looking up the external interface's address for every single packet.  But
    # it requires this code to know that address and it requires that if it
    # ever changes the rule gets updated.  So we'll just masquerade for now.
    postrouting = [
        b"iptables",

        # We're still in NAT-land.
        b"-t", b"nat",

        # As described above, this transformation happens after routing
        # decisions have been made and the packet is on its way out of the
        # system.
        b"-A", b"POSTROUTING",

        # We'll stick to matching the same kinds of packets we matched in the
        # earlier stage.  We might want to change the factoring of this code to
        # avoid the duplication - particularly in case we want to change the
        # specifics of the filter.
        b"--protocol", b"tcp",
        b"--dport", unicode(port).encode("ascii"),

        # Do the masquerading.
        b"-j", b"MASQUERADE",
    ]

    # Secret level!!  Traffic that originates *on* the host bypasses the
    # PREROUTING chain.  Instead, it passes through the OUTPUT chain.  If we
    # want connections from localhost to the forwarded port to be affected then
    # we need a rule in the OUTPUT chain to do the same kind of DNAT that we
    # did in the PREROUTING chain.
    output = [
        b"iptables",

        # Yep, still in NAT-land.
        b"-t", b"nat",

        # As mentioned, this rule is for the OUTPUT chain.
        b"-A", b"OUTPUT",

        # Matching exactly the same kinds of packets as the other two rules are
        # matching.
        b"--protocol", b"tcp",
        b"--dport", unicode(port).encode("ascii"),

        # Do the same DNAT as we did in the rule for the PREROUTING chain.
        b"-j", b"DNAT",
        b"--to-destination", unicode(ip).encode("ascii"),
    ]

    # The network stack only considers forwarding traffic when certain system
    # configuration is in place.
    with open(b"/proc/sys/net/ipv4/conf/default/forwarding", "wt") as forwarding:
        forwarding.write(b"1")

    # In order to have the OUTPUT chain DNAT rule affect routing decisions, we
    # also need to tell the system to make routing decisions about traffic from
    # or to localhost.
    with open(b"/proc/sys/net/ipv4/conf/default/route_localnet", "wt") as route_localnet:
        route_localnet.write(b"1")

    def run(command):
        finished = Deferred()
        connecting = connectProtocol(
            ProcessEndpoint(reactor, command[0], command, env=environ),
            Collector(finished))
        connecting.addCallback(lambda ignored: finished)
        return connecting

    configuring = gatherResults([run(prerouting), run(postrouting), run(output)])
    return configuring
