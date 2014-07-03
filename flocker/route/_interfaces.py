# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Definitions of interfaces related to network configuration.
"""

from zope.interface import Interface


class INetwork(Interface):
    """
    An ``INetwork`` can have proxies configured on it.
    """
    def create_proxy_to(ip, port):
        """
        Create a new TCP proxy to ``ip`` on port ``port``.

        :param ip: The destination to which to proxy.
        :type ip: ipaddr.IPv4Address

        :param int port: The TCP port number on which to proxy.

        :return: An object representing the created proxy.  Primarily useful as
            an argument to :py:meth:`delete_proxy`.
        """

    def delete_proxy(proxy):
        """
        Delete an existing TCP proxy previously created using
        :py:meth:`create_proxy_to`.

        :param proxy: The object returned by :py:meth:`create_proxy_to` or one
            of the elements of the sequence returned by
            :py:meth:`enumerate_proxies`.
        """

    def enumerate_proxies():
        """
        Retrieve configured proxy information.

        :return: A :py:class:`list` of objects describing all configured
            proxies.
        """
