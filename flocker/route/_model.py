# Copyright ClusterHQ Inc.  See LICENSE file for details.
# -*- test-case-name: flocker.route.test.test_model -*-

"""
Objects related to the representation of Flocker-controlled network state.
"""

from pyrsistent import PClass, field


class Proxy(PClass):
    """
    :ivar ipaddr.IPv4Address ip: The IPv4 address towards which this proxy
        directs traffic.

    :ivar int port: The TCP port number on which this proxy operates.
    """
    ip = field(mandatory=True)
    port = field(type=int, mandatory=True)


class OpenPort(PClass):
    """
    :ivar int port: The TCP port which is opened.
    """
    port = field(type=int, mandatory=True)
