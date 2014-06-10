# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
# -*- test-case-name: flocker.route.test_create -*-

"""
Manipulate network routing behavior on a node using ``iptables``.
"""

from __future__ import unicode_literals

from collections import namedtuple
from subprocess import check_output

from ipaddr import IPAddress

from twisted.python.filepath import FilePath

FLOCKER_COMMENT_MARKER = b"flocker create_proxy_to"

iptables_options = namedtuple(
    "iptables_options", "comment destination_port to_destination")


class Proxy(namedtuple("Proxy", "ip port")):
    """
    :ivar ipaddr.IPv4Address ip: The IPv4 address towards which this proxy
        directs traffic.

    :ivar int port: The TCP port number on which this proxy operates.
    """


def create_proxy_to(ip, port):
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
    encoded_ip = unicode(ip).encode("ascii")
    encoded_port = unicode(port).encode("ascii")

    # The first goal is to configure "Destination NAT" (DNAT).  We're just
    # going to rewrite the destination address of traffic arriving on the
    # specified port so it looks like it is destined for the specified ip
    # instead of destined for "us".  This gets the packets delivered to the
    # right destination.
    check_output([
            b"iptables",

            # All NAT stuff happens in the netfilter NAT table.
            b"--table", b"nat",

            # Destination NAT has to happen "pre"-routing so that the normal
            # routing rules on the machine will use the re-written destination
            # address and get the packet to that new destination.  Accomplish
            # this by appending the rule to the PREROUTING chain.
            b"--append", b"PREROUTING",

            # Only re-route traffic with a destination port matching the one we
            # were told to manipulate.  It is also necessary to specify TCP (or
            # UDP) here since that is the layer of the network stack that
            # defines ports.
            b"--protocol", b"tcp", b"--destination-port", encoded_port,

            # And only re-route traffic directed at this host.  Traffic
            # originating on this host directed at some random other host that
            # happens to be on the same port should be left alone.
            b"--match", b"addrtype", b"--dst-type", b"LOCAL",

            # Tag it as a flocker-created rule so we can recognize it later.
            b"--match", b"comment", b"--comment", FLOCKER_COMMENT_MARKER,

            # If the filter matched, jump to the DNAT chain to handle doing the
            # actual packet mangling.  DNAT is a built-in chain that already
            # knows how to do this.  Pass an argument to the DNAT chain so it
            # knows how to mangle the packet - rewrite the destination IP of
            # the address to the target we were told to use.
            b"--jump", b"DNAT", b"--to-destination", encoded_ip,
    ])

    # Bonus round!  Having performed DNAT (changing the destination) during
    # prerouting we are now prepared to send the packet on somewhere else.  On
    # its way out of this system it is also necessary to further modify and
    # then track that packet.  We want it to look like it comes from us (the
    # downstream client will be *very* confused if the node we're passing the
    # packet on to replies *directly* to them; and by confused I mean it will
    # be totally broken, of course) so we also need to "masquerade" in the
    # postrouting chain.  This changes the source address (ip and port) of the
    # packet to the address of the external interface the packet is exiting
    # upon.  Doing SNAT here would be a little bit more efficient because the
    # kernel could avoid looking up the external interface's address for every
    # single packet.  But it requires this code to know that address and it
    # requires that if it ever changes the rule gets updated and it may require
    # some steps to do port allocation (not sure what they are yet).  So we'll
    # just masquerade for now.
    check_output([
            b"iptables",

            # All NAT stuff happens in the netfilter NAT table.
            b"--table", b"nat",

            # As described above, this transformation happens after routing
            # decisions have been made and the packet is on its way out of the
            # system.  Therefore, append the rule to the POSTROUTING chain.
            b"--append", b"POSTROUTING",

            # We'll stick to matching the same kinds of packets we matched in
            # the earlier stage.  We might want to change the factoring of this
            # code to avoid the duplication - particularly in case we want to
            # change the specifics of the filter.
            #
            # This omits the LOCAL addrtype check, though, because at this
            # point the packet is definitely leaving this host.
            b"--protocol", b"tcp", b"--destination-port", encoded_port,

            # Do the masquerading.
            b"--jump", b"MASQUERADE",
    ])

    # Secret level!!  Traffic that originates *on* the host bypasses the
    # PREROUTING chain.  Instead, it passes through the OUTPUT chain.  If we
    # want connections from localhost to the forwarded port to be affected then
    # we need a rule in the OUTPUT chain to do the same kind of DNAT that we
    # did in the PREROUTING chain.
    check_output([
            b"iptables",

            # All NAT stuff happens in the netfilter NAT table.
            b"--table", b"nat",

            # As mentioned, this rule is for the OUTPUT chain.
            b"--append", b"OUTPUT",

            # Matching the exact same kinds of packets as the PREROUTING rule
            # matches.
            b"--protocol", b"tcp",
            b"--destination-port", encoded_port,
            b"--match", b"addrtype", b"--dst-type", b"LOCAL",

            # Do the same DNAT as we did in the rule for the PREROUTING chain.
            b"--jump", b"DNAT", b"--to-destination", encoded_ip,
    ])

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

    return Proxy(ip, port)


def enumerate_proxies():
    """
    Retrieve configured proxy information.

    :return: A :py:class:`list` of objects describing all configured proxies.
    """
    proxies = []
    for rule in get_flocker_rules():
        proxies.append(Proxy(rule.to_destination, rule.destination_port))

    return proxies


def get_flocker_rules():
    """
    Look up all of the iptables rules created/managed by flocker.

    :return: An iterator of :py:class:`iptables_options` instances, one for
        each rule found.
    """
    # Life is horrible.
    # https://stackoverflow.com/questions/109553/how-can-i-programmatically-manage-iptables-rules-on-the-fly
    output = check_output([b"iptables-save"])

    # Find the beginning of the NAT table
    header = b"*nat\n"
    begin = output.find(header) + len(header)

    # Find the end of the NAT table
    footer = b"COMMIT\n"
    end = output.find(footer, begin)

    # Slice it out.
    nat = output[begin:end]

    for line in nat.splitlines():
        if line.startswith(b":"):
            # Skip these lines describing a chain or the table overall.
            continue

        options = parse_iptables_options(line.split())

        if options.comment == FLOCKER_COMMENT_MARKER:
            yield options


def parse_iptables_options(argv):
    """
    Parse a single line of iptables-save(8) output from the NAT table section.

    :param argv: A :py:class:`list` of :py:class:`bytes` instances like an
        iptables argv (not including ``b"iptables"`` as ``argv[0]``).

    :return: A :py:class:`iptables_options` instance holding the values taken
        from ``argv``.
    """
    # "Parsing" things like this:
    #
    # -A PREROUTING -p tcp -m tcp --dport 4567 -m addrtype --dst-type LOCAL
    #     -m comment --comment flocker -j DNAT --to-destination 10.1.2.3
    #
    # -A OUTPUT -p tcp -m tcp --dport 4567 -m addrtype --dst-type LOCAL -j DNAT
    #     --to-destination 10.1.2.3
    #
    # -A POSTROUTING -p tcp -m tcp --dport 4567 -j MASQUERADE
    #
    # To avoid having to know about every single possible current and future
    # iptables option, don't try to parse the whole line.  Just look for things
    # we expect and recognize.
    comment = None
    destination_port = None
    to_destination = None

    try:
        destination_port_index = argv.index(b"--dport")
        destination_port = int(argv[destination_port_index + 1])

        to_destination_index = argv.index(b"--to-destination")
        to_destination = IPAddress(argv[to_destination_index + 1])

        # Find the comment last so that the other two attributes always have a
        # value if the comment has a value.
        comment_index = argv.index(b"--comment")
        comment = argv[comment_index + 1]
    except (IndexError, ValueError):
        pass

    return iptables_options(comment, destination_port, to_destination)
