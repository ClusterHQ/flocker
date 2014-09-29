# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Objects related to an in-memory implementation of ``INetwork``.
"""

from zope.interface import implementer
from eliot import Logger

from ._interfaces import INetwork
from ._model import Proxy


@implementer(INetwork)
class MemoryNetwork(object):
    """
    An isolated, in-memory-only implementation of ``INetwork``.

    :ivar set _proxies: A ``set`` of ``Proxy`` instances representing all of
        the proxies supposedly configured on this network.
    """
    logger = Logger()

    def __init__(self, used_ports):
        self._proxies = set()
        self._used_ports = used_ports

    def create_proxy_to(self, ip, port):
        proxy = Proxy(ip=ip, port=port)
        self._proxies.add(proxy)
        return proxy

    def delete_proxy(self, proxy):
        self._proxies.remove(proxy)

    def enumerate_proxies(self):
        return list(self._proxies)

    def enumerate_used_ports(self):
        proxy_ports = frozenset(proxy.port for proxy in self._proxies)
        return proxy_ports | self._used_ports


def make_memory_network(used_ports=frozenset()):
    """
    Create a new, isolated, in-memory-only provider of ``INetwork``.

    :param frozenset used_ports: Some port numbers which are to be considered
        already used and included in the result of ``enumerate_used_ports``
        when called on the returned object.
    """
    return MemoryNetwork(used_ports=used_ports)
