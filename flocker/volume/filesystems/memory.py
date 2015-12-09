# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""In-memory fake filesystem APIs, for use with unit tests."""

from __future__ import absolute_import

from errno import ENOENT
from contextlib import contextmanager
from tarfile import TarFile
from io import BytesIO

from zope.interface import implementer

from characteristic import with_init, with_cmp, with_repr

from twisted.internet.defer import succeed, fail
from twisted.application.service import Service

from .errors import MaximumSizeTooSmall
from .interfaces import (
    IFilesystemSnapshots, IStoragePool, IFilesystem,
    FilesystemAlreadyExists)
from .zfs import Snapshot

from .._model import VolumeSize


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
@with_cmp(["path"])
@with_repr(["path", "size"])
@with_init(["path", "size"],
           defaults=dict(size=VolumeSize(maximum_size=None)))
class DirectoryFilesystem(object):
    """
    A directory pretending to be an independent filesystem.

    Snapshots are also supported in a pretend way.  A file is kept in the
    directory recording the names of snapshots which supposedly have been
    taken.  No other state related to snapshots is tracked (eg, the state of
    the directory at the time of those snapshots is not recorded).

    :ivar FilePath path: The directory where data for this "filesystem" is
        stored.
    """
    def get_path(self):
        return self.path

    def _snapshots(self):
        """
        Load the pretend snapshot data.

        :return: A ``list`` of ``Snapshot`` instances.  These will correspond
            to the pretend snapshots taken by the ``snapshot`` method.
        """
        try:
            data = self.get_path().child(b".snapshots").getContent()
        except IOError as e:
            if e.errno != ENOENT:
                raise
            snapshots = []
        else:
            snapshots = [
                Snapshot(name=name)
                for name
                in data.splitlines()
            ]
        return snapshots

    def snapshots(self):
        """
        Retrieve the snapshots which were previously taken, for pretend.
        """
        return succeed(self._snapshots())

    def snapshot(self, name):
        """
        Pretend to take a snapshot.  Assign it the given name.
        """
        self.get_path().child(b".snapshots").setContent(
            b"\n".join([
                snapshot.name for snapshot in self._snapshots()] + [name])
        )

    @contextmanager
    def reader(self, remote_snapshots=None):
        """
        Package up filesystem contents as a tarball.
        """
        result = BytesIO()
        tarball = TarFile(fileobj=result, mode="w")
        for child in self.path.children():
            tarball.add(child.path, arcname=child.basename(), recursive=True)
        tarball.close()

        # You can append anything to the end of a tar stream without corrupting
        # it.  Smuggle some data about the snapshots through here.  This lets
        # tests verify that an incremental stream is really being produced
        # without forcing us to implement actual incremental streams on top of
        # dumb directories.
        if remote_snapshots:
            result.write(
                u"\nincremental stream based on\n{}".format(
                    u"\n".join(snapshot.name for snapshot in remote_snapshots)
                ).encode("ascii")
            )
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
            # https://clusterhq.atlassian.net/browse/FLOC-122
            pass


@implementer(IStoragePool)
class FilesystemStoragePool(Service):
    """
    A :class:`IStoragePool` implementation that just creates directories.

    Rather than mounting actual filesystems, they are emulated by simply
    creating a directory for each filesystem.
    """
    def __init__(self, root):
        """
        :param FilePath root: The root directory.
        """
        self._root = root
        if not self._root.exists():
            self._root.createDirectory()

    def create(self, volume):
        filesystem = self.get(volume)
        root = filesystem.get_path()
        root.makedirs()
        if volume.size.maximum_size is not None:
            root.child(b".size").setContent(
                u"{0}".format(volume.size.maximum_size).encode("ascii"))
        return succeed(filesystem)

    def destroy(self, volume):
        filesystem = self.get(volume)
        root = filesystem.get_path()
        root.remove()
        return succeed(None)

    def set_maximum_size(self, volume):
        filesystem = self.get(volume)
        root = filesystem.get_path()

        def get_size():
            total_size = 0
            for f in root.walk():
                if not f.isdir():
                    total_size += f.getsize()
            return total_size

        current_size = get_size()
        size_path = root.child(b".size")
        if volume.size.maximum_size is not None:
            if volume.size.maximum_size < current_size:
                raise MaximumSizeTooSmall()
            size_path.setContent(
                u"{0}".format(volume.size.maximum_size).encode("ascii"))
        elif size_path.exists():
            size_path.remove()
        return succeed(filesystem)

    def clone_to(self, parent, volume):
        parent = self.get(parent)
        child = self.get(volume)
        if child.get_path().exists():
            return fail(FilesystemAlreadyExists())

        d = self.create(volume)
        with parent.reader() as reader:
            with child.writer() as writer:
                writer.write(reader.read())
        return d

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
                volume.node_id.encode("ascii"), volume.name.to_bytes())),
            size=volume.size)

    def enumerate(self):
        filesystems = set()
        if self._root.isdir():
            for path in self._root.children():
                if path.child(b".size").exists():
                    maximum_size = int(
                        path.child(b".size").getContent().decode("ascii"))
                else:
                    maximum_size = None
                filesystems.add(
                    DirectoryFilesystem(
                        path=path,
                        size=VolumeSize(maximum_size=maximum_size),
                    )
                )
        return succeed(filesystems)
