# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
# -*- test-case-name: flocker.route.test_create -*-

"""
Manipulate network routing behavior on a node using ``iptables``.
"""

from __future__ import unicode_literals

from collections import namedtuple

from iptc import Chain, Rule, Table

from twisted.python.filepath import FilePath


class _Proxy(namedtuple("_Proxy", "ip port")):
    """
    :ivar ipaddr.IPv4Address ip: The IPv4 address towards which this proxy
        directs traffic.

    :ivar int port: The TCP port number on which this proxy operates.
    """


def create(ip, port):
    """
    Create a new TCP proxy to `ip` on port `port`.

    :param ip: The destination to which to proxy.
    :type ip: ipaddr.IPv4Address

    :param int port: The TCP port number on which to proxy.

    :return: None
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

    # All NAT stuff happens in the netfilter NAT table.
    nat = Table(Table.NAT)

    rule = Rule()

    # Only re-route traffic with a destination port matching the one we were
    # told to manipulate.  It is also necessary to specify TCP (or UDP) here
    # since that is the layer of the network stack that defines ports.
    rule.protocol = b"tcp"
    tcp = rule.create_match(b"tcp")
    tcp.dport = unicode(port).encode("ascii")

    # And only re-route traffic directed at this host.  Traffic originating on
    # this host directed at some random other host that happens to be on the
    # same port should be left alone.
    local = rule.create_match(b"addrtype")
    local.dst_type = b"LOCAL"

    # If the filter matched, jump to the DNAT chain to handle doing the actual
    # packet mangling.  DNAT is a built-in chain that already knows how to do
    # this.
    dnat = rule.create_target(b"DNAT")

    # Pass an argument to the DNAT chain so it knows how to mangle the packet -
    # rewrite the destination IP of the address to the target we were told to
    # use.
    dnat.to_destination = unicode(ip).encode("ascii")

    # Destination NAT has to happen "pre"-routing so that the normal routing
    # rules on the machine will use the re-written destination address and get
    # the packet to that new destination.  Accomplish this by appending the
    # rule to the PREROUTING chain.
    prerouting = Chain(nat, b"PREROUTING")
    prerouting.append_rule(rule)

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

    rule = Rule()

    # We'll stick to matching the same kinds of packets we matched in the
    # earlier stage.  We might want to change the factoring of this code to
    # avoid the duplication - particularly in case we want to change the
    # specifics of the filter.
    #
    # This omits the LOCAL addrtype check because at this point the packet is
    # definitely leaving this host.
    rule.protocol = b"tcp"
    tcp = rule.create_match(b"tcp")
    tcp.dport = unicode(port).encode("ascii")

    # Do the masquerading.
    rule.create_target(b"MASQUERADE")

    # As described above, this transformation happens after routing decisions
    # have been made and the packet is on its way out of the system.
    # Therefore, append the rule to the POSTROUTING chain.
    postrouting = Chain(nat, b"POSTROUTING")
    postrouting.append_rule(rule)

    # Secret level!!  Traffic that originates *on* the host bypasses the
    # PREROUTING chain.  Instead, it passes through the OUTPUT chain.  If we
    # want connections from localhost to the forwarded port to be affected then
    # we need a rule in the OUTPUT chain to do the same kind of DNAT that we
    # did in the PREROUTING chain.

    rule = Rule()

    # Matching the exact same kinds of packets as the PREROUTING rule matches.
    rule.protocol = b"tcp"
    tcp = rule.create_match(b"tcp")
    tcp.dport = unicode(port).encode("ascii")
    local = rule.create_match(b"addrtype")
    local.dst_type = b"LOCAL"

    # Do the same DNAT as we did in the rule for the PREROUTING chain.
    dnat = rule.create_target(b"DNAT")
    dnat.to_destination = unicode(ip).encode("ascii")

    # As mentioned, this rule is for the OUTPUT chain.
    output = Chain(nat, b"OUTPUT")
    output.append_rule(rule)

    # The network stack only considers forwarding traffic when certain system
    # configuration is in place.
    #
    # https://www.kernel.org/doc/Documentation/networking/ip-sysctl.txt will
    # explain the meaning of these in (very slightly) more detail.
    conf = FilePath(b"/proc/sys/net/ipv4/conf")
    with conf.descendant([b"default", b"forwarding"]).open("wb") as forwarding:
        forwarding.write(b"1")

    # In order to have the OUTPUT chain DNAT rule affect routing decisions, we
    # also need to tell the system to make routing decisions about traffic from
    # or to localhost.
    for path in conf.children():
        with path.child(b"route_localnet").open("wb") as route_localnet:
            route_localnet.write(b"1")

    return _Proxy(ip, port)


def enumerate_proxies():
    """
    Retrieve configured proxy information.

    :return: A :py:class:`list` of objects describing all configured proxies.
    """
    return []
