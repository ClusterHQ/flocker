# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Helpers for :py:class:`~twisted.python.filepath.FilePath`.
"""


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
