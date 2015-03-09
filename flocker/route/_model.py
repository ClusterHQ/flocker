# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
# -*- test-case-name: flocker.route.test.test_model -*-

"""
Objects related to the representation of Flocker-controlled network state.
"""

from pyrsistent import PRecord, field


class Proxy(PRecord):
    """
    :ivar ipaddr.IPv4Address ip: The IPv4 address towards which this proxy
        directs traffic.

    :ivar int port: The TCP port number on which this proxy operates.
    """
    ip = field()
    port = field(type=int)


class OpenPort(PRecord):
    """
    :ivar int port: The TCP port which is opened.
    """
    port = field(type=int)
