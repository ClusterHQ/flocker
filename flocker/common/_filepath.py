# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Helpers for :py:class:`~twisted.python.filepath.FilePath`.
"""


def make_file(path, content='', permissions=None):
    """
    Create a file with given content and permissions.

    :param FilePath path: Path to create the file.
    :param str content: Content to write to the file. If not specified,
    :param int permissions: Unix file permissions to be passed to ``chmod``.
    """
    path.setContent(content)
    if permissions is not None:
        path.chmod(permissions)
