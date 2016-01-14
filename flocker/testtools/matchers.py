# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
testtools matchers used in Flocker tests.
"""

from testtools.matchers import (
    AfterPreprocessing,
    DirExists,
    FileExists,
    MatchesAll,
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


def _get_content(file_path):
    """
    Get content for ``file_path``.
    """
    return file_path.getContent()


def file_contents(matcher):
    """
    Match if a files contents match ``matcher``.

    For example::

        self.assertThat('/foo/bar/baz', file_contents(Equals('hello world')))

    Will match if there is a file ``/foo/bar/baz`` and if its contents are
    exactly ``hello world``.
    """
    # We don't use ``FileContains``, as that raises an IOError if the path is
    # for an existing directory.
    return MatchesAll(
        file_exists(),
        AfterPreprocessing(_get_content, matcher, annotate=False),
        first_only=True,
    )
