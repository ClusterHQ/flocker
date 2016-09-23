# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Helpers for :py:class:`~twisted.python.filepath.FilePath`.
"""
from tempfile import mkdtemp

from twisted.python.filepath import FilePath, IFilePath
from twisted.python.components import proxyForInterface


def make_file(path, content='', permissions=None):
    """
    Create a file with given content and permissions.

    Don't use this for sensitive content, as the permissions are applied
    *after* the data is written to the filesystem.

    :param FilePath path: Path to create the file.
    :param str content: Content to write to the file. If not specified,
    :param int permissions: Unix file permissions to be passed to ``chmod``.

    :return: ``path``, unmodified.
    :rtype: :py:class:`twisted.python.filepath.FilePath`
    """
    path.setContent(content)
    if permissions is not None:
        path.chmod(permissions)
    return path


def make_directory(path):
    """
    Create a directory at ``path``.

    :param FilePath path: The place to create a directory.

    :raise OSError: If path already exists and is not a directory.
    :return: ``path``, unmodified.
    :rtype: :py:class:`twisted.python.filepath.FilePath`
    """
    if not path.isdir():
        path.makedirs()
    return path


class _TemporaryPath(proxyForInterface(IFilePath, "_path")):
    """
    An ``IFilePath`` which when used as a context manager will remove itself.
    """
    def __init__(self, path):
        self._path = path

    @property
    def path(self):
        return self._path.path

    def remove(self):
        return self._path.remove()

    def __eq__(self, other):
        return self._path == other

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.remove()

    def __repr__(self):
        return repr(self._path)


def temporary_directory(parent_path=None):
    """
    :returns: A temporary directory (a ``_TemporaryPath``).
    """
    mkdtemp_args = {}
    if parent_path is not None:
        mkdtemp_args["dir"] = parent_path.path

    return _TemporaryPath(
        path=FilePath(mkdtemp(**mkdtemp_args))
    )
