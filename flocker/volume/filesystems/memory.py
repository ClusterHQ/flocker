# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""In-memory fake filesystem APIs, for use with unit tests."""

from __future__ import absolute_import

from zope.interface import implementer

from characteristic import attributes

from twisted.internet.defer import succeed

from .interfaces import IFilesystemSnapshots, IStoragePool, IFilesystem


@implementer(IFilesystemSnapshots)
class CannedFilesystemSnapshots(object):
    """In-memory filesystem snapshotter."""
    def __init__(self, results):
        """
        :param results: A ``list`` of ``Deferred`` instances, results of calling
            ``create()``.
        """
        self._results = results
        self._snapshots = []

    def create(self, name):
        d = self._results.pop(0)
        d.addCallback(lambda _: self._snapshots.append(name))
        return d

    def list(self):
        return succeed(self._snapshots)


@implementer(IFilesystem)
@attributes(["mountpoint"])
class DirectoryFilesystem(object):
    """A directory pretending to be an independent filesystem."""

    def get_mountpoint(self):
        return self.mountpoint


@implementer(IStoragePool)
class FilesystemStoragePool(object):
    """A :class:`IStoragePool` implementation that just creates directories.

    Rather than mounting actual filesystems, they are emulated by simply
    creating a directory for each filesystem.
    """
    def __init__(self, root):
        """
        :param FilePath root: The root directory.
        """
        self._root = root

    def create(self, volume):
        filesystem = self.get(volume)
        filesystem.get_mountpoint().makedirs()
        return succeed(filesystem)

    def get(self, volume):
        return DirectoryFilesystem(
            mountpoint=self._root.child(b"%s.%s" % (
                volume.uuid.encode("ascii"), volume.name.encode("ascii"))))
