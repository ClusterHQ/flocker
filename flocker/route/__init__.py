# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
# -*- test-case-name: flocker.route.test -*-

"""
Management APIs for network routing functionality.

Containers are exposed to the world via ``external routes``.  For example, a
web service might have an ``external route`` defined as TCP port 443.  This
will allow clients expecting to be able to make HTTPS requests to the software
in the container to connect to the host running the container and have their
traffic forwarded into the container.  It also allows clients to contact any
other cooperating node on TCP port 443.  Those nodes will act as a relay
between the client and the correct node.  With a DNS configuration that
includes address records for the website hostname for all cooperating nodes
this allows easy, transparent migration of containers between any of the
cooperating nodes.
"""

__all__ = ["create_proxy_to", "delete_proxy", "enumerate_proxies"]

from ._iptables import create_proxy_to, delete_proxy, enumerate_proxies
