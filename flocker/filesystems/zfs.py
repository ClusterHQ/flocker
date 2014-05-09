# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
ZFS APIs.
"""

from __future__ import absolute_import

import os
from collections import namedtuple

from zope.interface import implementer

from twisted.internet.endpoints import ProcessEndpoint, connectProtocol
from twisted.internet.protocol import Protocol

from .interfaces import IFilesystemSnapshots
from ..snapshots import SnapshotName


class CommandFailed(Exception):
    """
    The ``zfs`` command failed for some reasons.
    """



class BadArguments(Exception):
    """
    The ``zfs`` command was called with incorrect arguments.
    """



def zfsCommand(reactor, arguments):
    """
    Run the ``zfs`` command-line tool with the given arguments.

    :param reactor: A ``IReactorProcess`` provider.

    :param arguments: A ``list`` of ``bytes``, command-line arguments to ``zfs``.

    :return: A :class:`Deferred` firing with the bytes of the result (on
        exit code 0), or errbacking with :class:`CommandFailed` or
        :class:`BadArguments` depending on the exit code (1 or 2).
    """
    endpoint = ProcessEndpoint(reactor, b"zfs", [b"zfs"] + arguments, os.environ)
    connectProtocol(endpoint, Protocol())



class Filesystem(namedtuple("Filesystem", "pool")):
    """
    A ZFS filesystem.

    For now the goal is simply not to pass bytes around when referring to a
    filesystem.  This will likely grow into a more sophisticiated
    implementation over time.

    :attr pool: The filesystem's pool name, e.g. ``b"hpool/myfs"``.
    """



#@implementer(IFilesystemSnapshots)
class ZFSSnapshots(object):
    def __init__(self, reactor, filesystem):
        #self._reactor = reactor
        #self._filesystem = filesystem
        pass


    def create(self, name):
        #encodedName = b"%s@%s" % (self._filesystem.pool, name.toBytes())
        #return zfsCommand(self._reactor, [b"snapshot", encodedName])
        pass


    def list(self):
        # d = zfsCommand(self._reactor, [b"-H", b"-r", b"-t", b"snapshot", b"-o",
        #                                b"name", b"-s", b"name",
        #                                self._filesystem.pool])
        # d.addCallback(lambda data:
        #               [SnapshotName.fromBytes(line.split(b"@", 1)[1])
        #                for line in data.splitlines()
        #                if line.startswith(b"%s@" % (self._filesystem.pool))])
        # return d
        pass
