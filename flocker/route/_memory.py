# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Objects related to an in-memory implementation of ``INetwork``.
"""

from zope.interface import implementer
from eliot import Logger

from ._interfaces import INetwork
from ._model import Proxy, OpenPort


@implementer(INetwork)
class MemoryNetwork(object):
    """
    An isolated, in-memory-only implementation of ``INetwork``.

    :ivar set _proxies: A ``set`` of ``Proxy`` instances representing all of
        the proxies supposedly configured on this network.
    """
    logger = Logger()

    def __init__(self):
        self._proxies = set()
        self._open_ports = set()

    def create_proxy_to(self, ip, port):
        proxy = Proxy(ip=ip, port=port)
        self._proxies.add(proxy)
        return proxy

    def delete_proxy(self, proxy):
        self._proxies.remove(proxy)

    def open_port(self, port):
        open_port = OpenPort(port=port)
        self._open_ports.add(open_port)
        return open_port

    def delete_open_port(self, open_port):
        self._open_ports.remove(open_port)

    def enumerate_proxies(self):
        return list(self._proxies)

    def enumerate_open_ports(self):
        return list(self._open_ports)


def make_memory_network():
    """
    Create a new, isolated, in-memory-only provider of ``INetwork``.
    """
    return MemoryNetwork()
