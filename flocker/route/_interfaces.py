# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Definitions of interfaces related to network configuration.
"""

from zope.interface import Attribute, Interface


class INetwork(Interface):
    """
    An ``INetwork`` can have proxies configured on it.
    """
    logger = Attribute(
        "An ``eliot.Logger`` instance used by this object to log its "
        "activities.  This is primarily intended as a testing hook which "
        "can be overridden to observe what log messages are written.")

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

    def open_port(port):
        """
        Create a new firewall opening for port ``port``.

        :param int port: The TCP port number to open.

        :return: An object representing the created open port.  Primarily
            useful as an argument to :py:meth:`delete_open_port`.
        """

    def delete_open_port(port):
        """
        Delete an existing firewall opening previously created using
        :py:meth:`open_port`.

        :param port: The object returned by :py:meth:`open_port` or one
            of the elements of the sequence returned by
            :py:meth:`enumerate_open_ports`.
        """

    def enumerate_proxies():
        """
        Retrieve configured proxy information.

        :return: A :py:class:`list` of objects describing all configured
            proxies.
        """

    def enumerate_open_ports():
        """
        Retrieve configured open port information.

        :return: A :py:class:`list` of objects describing all configured
            ports.
        """
