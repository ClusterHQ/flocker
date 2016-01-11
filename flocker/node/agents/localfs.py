"""
Testing implementation of ``IRemoteFilesystemAPI``.
"""

from uuid import UUID
from subprocess import check_call

from zope.interface import implementer

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
        return [RemoteFilesystem(dataset_id=UUID(child))
                for child in self.root.listdir()]

    def _child(self, dataset_id):
        return self.root.child(unicode(dataset_id))

    def create(self, dataset_id, metadata):
        self._child(dataset_id).mkdir()
        return RemoteFilesystem(dataset_id=dataset_id)

    def destroy(self, dataset_id):
        self._child(dataset_id).remove()

    def mount(self, dataset_id, path):
        check_call([b"mount", b"--bind", self._child(dataset_id).path,
                    path.path])

    def umount(self, dataset_id, path):
        check_call([b"umount", path.path])
