# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""In-memory fake filesystem APIs, for use with unit tests."""

from __future__ import absolute_import

from contextlib import contextmanager
from tarfile import TarFile
from io import BytesIO

from zope.interface import implementer

from characteristic import attributes

from twisted.internet.defer import succeed, fail

from .interfaces import (
    IFilesystemSnapshots, IStoragePool, IFilesystem,
    FilesystemAlreadyExists)


@implementer(IFilesystemSnapshots)
class CannedFilesystemSnapshots(object):
    """In-memory filesystem snapshotter."""
    def __init__(self, results):
        """
        :param results: A ``list`` of ``Deferred`` instances, results of
        calling ``create()``.
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
@attributes(["path"])
class DirectoryFilesystem(object):
    """A directory pretending to be an independent filesystem."""

    def get_path(self):
        return self.path

    @contextmanager
    def reader(self):
        """Package up filesystem contents as a tarball."""
        result = BytesIO()
        tarball = TarFile(fileobj=result, mode="w")
        for child in self.path.children():
            tarball.add(child.path, arcname=child.basename(), recursive=True)
        tarball.close()
        result.seek(0, 0)
        yield result

    @contextmanager
    def writer(self):
        """Expect written bytes to be a tarball."""
        result = BytesIO()
        yield result
        result.seek(0, 0)
        try:
            tarball = TarFile(fileobj=result, mode="r")
            if self.path.exists():
                self.path.remove()
            self.path.createDirectory()
            tarball.extractall(self.path.path)
        except:
            # This should really be dealt with, e.g. logged:
            # https://github.com/ClusterHQ/flocker/issues/122
            pass


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
        filesystem.get_path().makedirs()
        return succeed(filesystem)

    def change_owner(self, volume, new_volume):
        old_filesystem = self.get(volume)
        new_filesystem = self.get(new_volume)

        # There is a race condtion between checking whether the target exists,
        # and doing the move. If the target is created in between, the error
        # won't be reported correctly.  Since this is only used for testing,
        # assume there will be no race condition.
        if new_filesystem.get_path().exists():
            return fail(FilesystemAlreadyExists())

        old_filesystem.get_path().moveTo(new_filesystem.get_path())
        return succeed(new_filesystem)

    def get(self, volume):
        return DirectoryFilesystem(
            path=self._root.child(b"%s.%s" % (
                volume.uuid.encode("ascii"), volume.name.encode("ascii"))))

    def enumerate(self):
        if self._root.isdir():
            return succeed({
                DirectoryFilesystem(path=path)
                for path in self._root.children()})
        return succeed(set())
