# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
# -*- test-case-name: flocker.route.test_create -*-

"""
Manipulate network routing behavior on a node using ``iptables``.
"""

from __future__ import unicode_literals

from twisted.internet.protocol import Protocol
from twisted.internet.endpoints import ProcessEndpoint, connectProtocol

def create(reactor, ip, port):
    """
    Create a new TCP proxy to `ip` on port `port`.

    :param ip: The destination to which to proxy.
    :type ip: ipaddr.IPAddress

    :param port: The TCP port number on which to proxy.
    :type port: int
    """
    e = ProcessEndpoint(reactor, b"iptables", [b"iptables", b"stuff"])
    d = connectProtocol(e, Protocol())
    return d
