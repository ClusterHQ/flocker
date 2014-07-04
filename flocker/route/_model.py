# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Objects related to the representation of Flocker-controlled network state.
"""

from characteristic import attributes


@attributes(["ip", "port"])
class Proxy(object):
    """
    :ivar ipaddr.IPv4Address ip: The IPv4 address towards which this proxy
        directs traffic.

    :ivar int port: The TCP port number on which this proxy operates.
    """
