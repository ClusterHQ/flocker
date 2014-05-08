# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
ZFS APIs.
"""

from __future__ import absolute_import

from collections import namedtuple

from zope.interface import implementor

from .interfaces import IFilesystemSnapshots
from ..snapshots import SnapshotName


def zfsCommand(reactor, arguments):
    """
    Run the ``zfs`` command-line tool with the given arguments.

    :param reactor: A ``IReactorProcess`` provider.

    :param arguments: A ``list`` of ``bytes``, command-line arguments to ``zfs``.

    :return: A :class:`Deferred` firing with the bytes of the result (on
        exit code 0), or errbacking with :class:`CommandFailed` or
        :class:`BadArguments` depending on the exit code (1 or 2).
    """


class Filesystem(namedtuple("Filesystem", "pool")):
    """
    A ZFS filesystem.

    For now the goal is simply not to pass bytes around when referring to a
    filesystem.  This will likely grow into a more sophisticiated
    implementation over time.

    :attr pool: The filesystem's pool name, e.g. ``b"hpool/myfs"``.
    """



@implementor(IFilesystemSnapshots)
class ZFSSnapshots(object):
    def __init__(self, reactor, filesystem):
        self._reactor = reactor
        self._filesystem = filesystem


    def create(self, name):
        encodedName = b"%s@%s" % (self._filesystem.pool, name.toBytes())
        return zfsCommand(self._reactor, [b"snapshot", encodedName])


    def list(self):
        d = zfsCommand(self._reactor, [b"-H", b"-r", b"-t", b"snapshot", b"-o",
                                       b"name", b"-s", b"name",
                                       self._filesystem.pool])
        d.addCallback(lambda data:
                      [SnapshotName.fromBytes(line.split(b"@", 1)[1])
                       for line in data.splitlines()
                       if line.startswith(b"%s@" % (self._filesystem.pool))])
        return d
