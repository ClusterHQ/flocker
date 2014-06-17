# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""ZFS APIs."""

from __future__ import absolute_import

import os
import subprocess
from contextlib import contextmanager
from uuid import uuid4

from characteristic import with_cmp, with_repr

from zope.interface import implementer

from twisted.internet.endpoints import ProcessEndpoint, connectProtocol
from twisted.internet.protocol import Protocol
from twisted.internet.defer import Deferred
from twisted.internet.error import ConnectionDone, ProcessTerminated

from .interfaces import IFilesystemSnapshots, IStoragePool, IFilesystem
from ..snapshots import SnapshotName


def random_name():
    """Return a random pool name.

    :return: Random ``bytes``.
    """
    return os.urandom(8).encode("hex")


class CommandFailed(Exception):
    """The ``zfs`` command failed for some reasons."""


class BadArguments(Exception):
    """The ``zfs`` command was called with incorrect arguments."""


class _AccumulatingProtocol(Protocol):
    """
    Accumulate all received bytes.
    """

    def __init__(self):
        self._result = Deferred()
        self._data = b""

    def dataReceived(self, data):
        self._data += data

    def connectionLost(self, reason):
        if reason.check(ConnectionDone):
            self._result.callback(self._data)
        elif reason.check(ProcessTerminated) and reason.value.exitCode == 1:
            self._result.errback(CommandFailed())
        elif reason.check(ProcessTerminated) and reason.value.exitCode == 2:
            self._result.errback(BadArguments())
        else:
            self._result.errback(reason)
        del self._result


def zfs_command(reactor, arguments):
    """Run the ``zfs`` command-line tool with the given arguments.

    :param reactor: A ``IReactorProcess`` provider.

    :param arguments: A ``list`` of ``bytes``, command-line arguments to
    ``zfs``.

    :return: A :class:`Deferred` firing with the bytes of the result (on
        exit code 0), or errbacking with :class:`CommandFailed` or
        :class:`BadArguments` depending on the exit code (1 or 2).
    """
    endpoint = ProcessEndpoint(reactor, b"zfs", [b"zfs"] + arguments,
                               os.environ)
    d = connectProtocol(endpoint, _AccumulatingProtocol())
    d.addCallback(lambda protocol: protocol._result)
    return d


@implementer(IFilesystem)
@with_cmp(["pool", "dataset"])
@with_repr(["pool", "dataset"])
class Filesystem(object):
    """A ZFS filesystem.

    For now the goal is simply not to pass bytes around when referring to a
    filesystem.  This will likely grow into a more sophisticiated
    implementation over time.
    """
    def __init__(self, pool, dataset, mountpoint=None):
        """
        :param pool: The filesystem's pool name, e.g. ``b"hpool"``.

        :param dataset: The filesystem's dataset name, e.g. ``b"myfs"``, or
            ``None`` for the top-level filesystem.

        :param twisted.python.filepath.FilePath mountpoint: Where the
            filesystem is mounted.
        """
        self.pool = pool
        self.dataset = dataset
        self._mountpoint = mountpoint

    @property
    def name(self):
        """The filesystem's full name, e.g. ``b"hpool/myfs"``."""
        if self.dataset is None:
            return self.pool
        return b"%s/%s" % (self.pool, self.dataset)

    def get_path(self):
        return self._mountpoint

    @contextmanager
    def reader(self):
        """Send zfs stream of contents."""
        # The existing snapshot code uses Twisted, so we're not using it
        # in this iteration.  What's worse, though, is that it's not clear
        # if the current snapshot naming scheme makes any sense, and
        # moreover it violates abstraction boundaries. So as first pass
        # I'm just using UUIDs, and hopefully requirements will become
        # clearer as we iterate.
        snapshot = b"%s@%s" % (self.name, uuid4())
        subprocess.check_call([b"zfs", b"snapshot", snapshot])
        process = subprocess.Popen([b"zfs", b"send", snapshot],
                                   stdout=subprocess.PIPE)
        try:
            yield process.stdout
        finally:
            process.stdout.close()
            process.wait()

    @contextmanager
    def writer(self):
        """Read in zfs stream."""
        # The temporary filesystem will be unnecessary once we have
        # https://github.com/hybridlogic/flocker/issues/46
        temp_filesystem = b"%s/%s" % (self.pool, random_name())
        process = subprocess.Popen([b"zfs", b"recv", b"-F", temp_filesystem],
                                   stdin=subprocess.PIPE)
        succeeded = False
        try:
            yield process.stdin
        finally:
            process.stdin.close()
            succeeded = not process.wait()
        if succeeded:
            subprocess.check_call([b"zfs", b"destroy", b"-R", self.name])
            subprocess.check_call([b"zfs", b"rename", temp_filesystem,
                                   self.name])
            subprocess.check_call([b"zfs", b"set",
                                   b"mountpoint=" + self._mountpoint.path,
                                   self.name])


@implementer(IFilesystemSnapshots)
class ZFSSnapshots(object):
    """Manage snapshots on a ZFS filesystem."""

    def __init__(self, reactor, filesystem):
        self._reactor = reactor
        self._filesystem = filesystem

    def create(self, name):
        encoded_name = b"%s@%s" % (self._filesystem.pool, name.to_bytes())
        d = zfs_command(self._reactor, [b"snapshot", encoded_name])
        d.addCallback(lambda _: None)
        return d

    def list(self):
        """List ZFS snapshots known to the volume manager.

        Snapshots whose names cannot be decoded are presumed not to be
        related to Flocker, and therefore will not be included in the
        result.
        """
        d = zfs_command(self._reactor,
                        [b"list", b"-H", b"-r", b"-t", b"snapshot", b"-o",
                         b"name", b"-s", b"name", self._filesystem.pool])

        def parse_snapshots(data):
            result = []
            for line in data.splitlines():
                pool, encoded_name = line.split(b'@', 1)
                if pool == self._filesystem.pool:
                    try:
                        result.append(SnapshotName.from_bytes(encoded_name))
                    except ValueError:
                        pass
            return result
        d.addCallback(parse_snapshots)
        return d


def volume_to_dataset(volume):
    """Convert a volume to a dataset name.

    :param flocker.volume.service.Volume volume: The volume.

    :return: Dataset name as ``bytes``.
    """
    # Include trunk in case we decide to do branch model later on:
    return b"%s.%s.trunk" % (volume.uuid.encode("ascii"),
                             volume.name.encode("ascii"))


@implementer(IStoragePool)
class StoragePool(object):
    """A ZFS storage pool."""

    def __init__(self, reactor, name, mount_root):
        """
        :param reactor: A ``IReactorProcess`` provider.
        :param bytes name: The pool's name.
        :param FilePath mount_root: Directory where filesystems should be
            mounted.
        """
        self._reactor = reactor
        self._name = name
        self._mount_root = mount_root

    def create(self, volume):
        filesystem = self.get(volume)
        mount_path = filesystem.get_path().path
        d = zfs_command(self._reactor,
                        [b"create",  b"-o", b"mountpoint=" + mount_path,
                         filesystem.name])
        d.addCallback(lambda _: filesystem)
        return d

    def get(self, volume):
        dataset = volume_to_dataset(volume)
        mount_path = self._mount_root.child(dataset)
        return Filesystem(self._name, dataset, mount_path)
