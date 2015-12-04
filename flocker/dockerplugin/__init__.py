# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Docker plugin allowing use of Flocker to manage Docker volumes.

This may eventually be a standalone package.
"""

from twisted.internet.address import UNIXAddress

# Many places in both twisted.web and Klein are unhappy with listening on
# Unix socket, e.g.  https://twistedmatrix.com/trac/ticket/5406.  The
# Docker plugin needs to listen using a Unix socket, so "fix" that by
# pretending we have a port number and host. Yes, I feel guilty.
UNIXAddress.port = 0
UNIXAddress.host = b"127.0.0.1"
del UNIXAddress
