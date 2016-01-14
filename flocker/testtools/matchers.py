# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
testtools matchers used in Flocker tests.
"""

from testtools.matchers import (
    AfterPreprocessing,
    DirExists,
    FileExists,
    PathExists,
)


def _filepath_to_path(filepath):
    """
    Convert FilePath to a regular path.
    """
    return filepath.path


def path_exists():
    """
    Match if a path exists on disk.
    """
    return AfterPreprocessing(_filepath_to_path, PathExists(), annotate=False)


def dir_exists():
    """
    Match if a directory exists on disk.
    """
    return AfterPreprocessing(_filepath_to_path, DirExists(), annotate=False)


def file_exists():
    """
    Match if a file exists on disk.
    """
    return AfterPreprocessing(_filepath_to_path, FileExists(), annotate=False)
