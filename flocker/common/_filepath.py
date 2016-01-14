# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Helpers for :py:class:`~twisted.python.filepath.FilePath`.
"""


def make_file(path, content, permissions):
    path.setContent(content)
    path.chmod(permissions)
