# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
# -*- test-case-name: flocker.route.test_create -*-

"""
Manipulate network routing behavior on a node using ``iptables``.
"""

from __future__ import unicode_literals

import shlex
from subprocess import check_call, check_output

from zope.interface import implementer
from ipaddr import IPAddress
from characteristic import attributes
from eliot import Logger
from psutil import net_connections
from twisted.python.filepath import FilePath

from ._logging import CREATE_PROXY_TO, DELETE_PROXY, IPTABLES, OPEN_PORT
from ._interfaces import INetwork
from ._model import Proxy, OpenPort

FLOCKER_PROXY_COMMENT_MARKER = b"flocker create_proxy_to"
FLOCKER_OPENPORT_COMMENT_MARKER = b"flocker open_port"


@attributes(["comment", "destination_port", "to_destination"])
class RuleOptions(object):
    """
    :ivar bytes comment: The value of the ``comment`` *match* for this rule.

    :ivar int destination_port: The value of the ``destination-port`` option
        for the ``tcp`` *match* for this rule.

    :ivar IPv4Address to_destination: The value of the ``to-destination``
        option for the ``DNAT`` *target* for this rule.
    """


def iptables(logger, argv):
    """
    Run ``iptables`` with the given arguments.

    :param list argv: A standard ``argv``-style argument list.  The path to
        iptables is prepended to this list for execution.
    """
    with IPTABLES(logger=logger, argv=argv):
        check_call([b"iptables"] + argv)


def create_proxy_to(logger, ip, port):
    """
    :see: ``HostNetwork.create_proxy_to``
    """
    action = CREATE_PROXY_TO(
        logger=logger, target_ip=ip, target_port=port)

    with action:
        encoded_ip = unicode(ip).encode("ascii")
        encoded_port = unicode(port).encode("ascii")

        # The first goal is to configure "Destination NAT" (DNAT).  We're just
        # going to rewrite the destination address of traffic arriving on the
        # specified port so it looks like it is destined for the specified ip
        # instead of destined for "us".  This gets the packets delivered to the
        # right destination.
        iptables(logger, [
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
            b"--match", b"comment", b"--comment", FLOCKER_PROXY_COMMENT_MARKER,

            # If the filter matched, jump to the DNAT chain to handle doing the
            # actual packet mangling.  DNAT is a built-in chain that already
            # knows how to do this.  Pass an argument to the DNAT chain so it
            # knows how to mangle the packet - rewrite the destination IP of
            # the address to the target we were told to use.
            b"--jump", b"DNAT", b"--to-destination", encoded_ip,
        ])

        # Bonus round!  Having performed DNAT (changing the destination) during
        # prerouting we are now prepared to send the packet on somewhere else.
        # On its way out of this system it is also necessary to further
        # modify and then track that packet.  We want it to look like it
        # comes from us (the downstream client will be *very* confused if
        # the node we're passing the packet on to replies *directly* to them;
        # and by confused I mean it will be totally broken, of course) so we
        # also need to "masquerade" in the postrouting chain.  This changes
        # the source address (ip and port) of the packet to the address of
        # the external interface the packet is exiting upon. Doing SNAT here
        # would be a little bit more efficient because the kernel could avoid
        # looking up the external interface's address for every single packet.
        # But it requires this code to know that address and it requires that
        # if it ever changes the rule gets updated and it may require some
        # steps to do port allocation (not sure what they are yet).  So we'll
        # just masquerade for now.
        iptables(logger, [
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
        # PREROUTING chain.  Instead, it passes through the OUTPUT chain.  If
        # we want connections from localhost to the forwarded port to be
        # affected then we need a rule in the OUTPUT chain to do the same kind
        # of DNAT that we did in the PREROUTING chain.
        iptables(logger, [
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

        iptables(logger, [
            b"--table", b"filter",
            b"--insert", b"FORWARD",

            b"--destination", encoded_ip,
            b"--protocol", b"tcp", b"--destination-port", encoded_port,

            b"--jump", b"ACCEPT",
        ])

        # The network stack only considers forwarding traffic when certain
        # system configuration is in place.
        #
        # https://www.kernel.org/doc/Documentation/networking/ip-sysctl.txt
        # will explain the meaning of these in (very slightly) more detail.
        conf = FilePath(b"/proc/sys/net/ipv4/conf")
        descendant = conf.descendant([b"default", b"forwarding"])
        with descendant.open("wb") as forwarding:
            forwarding.write(b"1")

        # In order to have the OUTPUT chain DNAT rule affect routing decisions,
        # we also need to tell the system to make routing decisions about
        # traffic from or to localhost.
        for path in conf.children():
            with path.child(b"route_localnet").open("wb") as route_localnet:
                route_localnet.write(b"1")

        return Proxy(ip=ip, port=port)


def open_port(logger, port):
    action = OPEN_PORT(
        logger=logger, target_port=port)

    with action:
        encoded_port = unicode(port).encode("ascii")
        iptables(logger, [
            b"--table", b"filter",
            b"--insert", b"INPUT",

            b"--protocol", b"tcp", b"--destination-port", encoded_port,

            # Tag it as a flocker-created rule so we can recognize it later.
            b"--match", b"comment",
            b"--comment", FLOCKER_OPENPORT_COMMENT_MARKER,

            b"--jump", b"ACCEPT",
        ])

    return OpenPort(port=port)


def delete_proxy(logger, proxy):
    """
    :see: ``HostNetwork.delete_proxy``
    """
    ip = unicode(proxy.ip).encode("ascii")
    port = unicode(proxy.port).encode("ascii")

    commands = [
        [b"--table", b"nat",
         b"--delete", b"PREROUTING",
         b"--protocol", b"tcp", b"--destination-port", port,
         b"--match", b"addrtype", b"--dst-type", b"LOCAL",
         b"--match", b"comment", b"--comment", FLOCKER_PROXY_COMMENT_MARKER,
         b"--jump", b"DNAT", b"--to-destination", ip],
        [b"--table", b"nat",
         b"--delete", b"POSTROUTING",
         b"--protocol", b"tcp", b"--destination-port", port,
         b"--jump", b"MASQUERADE"],
        [b"--table", b"nat",
         b"--delete", b"OUTPUT",
         b"--protocol", b"tcp", b"--destination-port", port,
         b"--match", b"addrtype", b"--dst-type", b"LOCAL",
         b"--jump", b"DNAT", b"--to-destination", ip],
        [b"--table", b"filter",
         b"--delete", b"FORWARD",
         b"--destination", ip,
         b"--protocol", b"tcp", b"--destination-port", port,
         b"--jump", b"ACCEPT"],
    ]

    with DELETE_PROXY(logger, target_ip=proxy.ip, target_port=proxy.port):
        for argv in commands:
            iptables(logger, argv)


def delete_port(logger, port):
    # FIXME
    action = OPEN_PORT(
        logger=logger, target_port=port)

    with action:
        encoded_port = unicode(port).encode("ascii")
        iptables(logger, [
            b"--table", b"filter",
            b"--delete", b"INPUT",

            b"--protocol", b"tcp", b"--destination-port", encoded_port,

            # Tag it as a flocker-created rule so we can recognize it later.
            b"--match", b"comment",
            b"--comment", FLOCKER_OPENPORT_COMMENT_MARKER,

            b"--jump", b"ACCEPT",
        ])


def enumerate_proxies():
    """
    Inspect the system's iptables configuration to determine what proxies
    currently exist.

    :see: :py:meth:`INetwork.enumerate_proxies` for parameter documentation.
    """
    proxies = []
    for rule in get_flocker_rules(FLOCKER_PROXY_COMMENT_MARKER):
        proxies.append(
            Proxy(ip=rule.to_destination, port=rule.destination_port))

    return proxies


def enumerate_open_ports():
    """
    Inspect the system's iptables configuration to determine which ports
    are currently open.

    :see: :py:meth:`INetwork.enumerate_proxies` for parameter documentation.
    """
    ports = []
    # TODO
    for rule in get_flocker_rules(FLOCKER_OPENPORT_COMMENT_MARKER):
        ports.append(
            OpenPort(port=rule.destination_port))

    return ports


def get_flocker_rules(comment_marker):
    """
    Look up all of the iptables rules created/managed by flocker.

    :return: An iterator of :py:class:`Options` instances, one for each rule
        found.
    """
    # Life is horrible.
    # https://stackoverflow.com/questions/109553/how-can-i-programmatically-manage-iptables-rules-on-the-fly
    # At least we know all the rules we need to inspect are in the NAT table.
    output = check_output([b"iptables-save", b"--table", b"nat"])

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

        options = parse_iptables_options(shlex.split(line))

        if options.comment == comment_marker:
            yield options


def parse_iptables_options(argv):
    """
    Parse a single line of iptables-save(8) output from the NAT table section.

    :param argv: A :py:class:`list` of :py:class:`bytes` instances like an
        iptables argv (not including ``b"iptables"`` as ``argv[0]``).

    :return: A :py:class:`RuleOptions` instance holding the values taken from
        ``argv``.
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
    except (IndexError, ValueError):
        destination_port = None

    try:
        to_destination_index = argv.index(b"--to-destination")
        to_destination = IPAddress(argv[to_destination_index + 1])
    except (IndexError, ValueError):
        to_destination = None

    try:
        comment_index = argv.index(b"--comment")
        comment = argv[comment_index + 1]
    except (IndexError, ValueError):
        comment = None

    return RuleOptions(
        comment=comment,
        destination_port=destination_port,
        to_destination=to_destination)


@implementer(INetwork)
class HostNetwork(object):
    """
    An ``INetwork`` implementation based on ``iptables``.
    """
    logger = Logger()

    def create_proxy_to(self, ip, port):
        """
        Configure iptables to proxy TCP traffic on the given port.

        :see: :meth:`INetwork.create_proxy_to` for parameter documentation.
        """
        return create_proxy_to(self.logger, ip, port)

    def delete_proxy(self, proxy):
        """
        Remove the iptables configuration which makes the given proxy work.

        :see: :meth:`INetwork.delete_proxy` for parameter documentation.
        """
        return delete_proxy(self.logger, proxy)

    def open_port(self, port):
        """
        Configure iptables to allow TCP traffic to the given port.
        """
        return open_port(self.logger, port)

    def delete_open_port(self, port):
        return delete_port(self.logger, port)

    enumerate_proxies = staticmethod(enumerate_proxies)

    enumerate_open_ports = staticmethod(enumerate_open_ports)

    def enumerate_used_ports(self):
        """
        Find all ports that are in use on this node by normal TCP servers or by
        proxies managed by this object.

        :see: :meth:`INetwork.enumerate_used_ports` for parameter
            documentation.
        """
        listening = set(
            conn.laddr[1]
            for conn
            in net_connections(kind='tcp')
        )
        proxied = set(
            proxy.port
            for proxy in self.enumerate_proxies()
        )
        open_ports = set(
            open_port.port
            for open_port in self.enumerate_open_ports()
        )
        # net_connections won't tell us about ports bound by sockets that
        # haven't entered the TCP state graph yet.
        return frozenset(listening | proxied | open_ports)


def make_host_network():
    """
    Create a new ``INetwork`` provider which will interact with the underlying
    system's network configuration.
    """
    return HostNetwork()
