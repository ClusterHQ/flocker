"""
Localhost implementation of ``IRemoteFilesystemAPI``, for testing.
"""

from uuid import UUID
from subprocess import check_call

from zope.interface import implementer

from twisted.python.filepath import FilePath

from .remotefs import IRemoteFilesystemAPI, RemoteFilesystem


@implementer(IRemoteFilesystemAPI)
class LocalFilesystem(object):
    """
    Local filesystem pretending to be remote filesystem.

    Can't be used for movement across nodes, but otherwise useful for testing.
    """
    def __init__(self, root):
        if not root.exists():
            root.makedirs()
        self.root = root()

    def list(self):
        return [self._to_fs(UUID(child))
                for child in self.root.listdir()]

    def _child(self, dataset_id):
        return self.root.child(unicode(dataset_id))

    def _to_fs(self, dataset_id):
        storage_path = self._child(dataset_id)
        local_mount_point = None
        for line in FilePath(
                b"/proc/self/mountinfo").getContent().splitlines():
            # let's pretend there's no spaces in paths...
            parts = line.split()
            origin = parts[3]
            destination = parts[4]
            if origin == storage_path.path:
                local_mount_point = FilePath(destination)
                break
        return RemoteFilesystem(dataset_id=dataset_id,
                                local_mount_point=local_mount_point)

    def create(self, dataset_id, metadata):
        self._child(dataset_id).mkdir()
        return self._to_fs(dataset_id)

    def destroy(self, dataset_id):
        self._child(dataset_id).remove()

    def mount(self, dataset_id, path):
        check_call([b"mount", b"--bind", self._child(dataset_id).path,
                    path.path])

    def umount(self, dataset_id, path):
        check_call([b"umount", path.path])
