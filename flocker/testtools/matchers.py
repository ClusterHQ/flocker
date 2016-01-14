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


def after(function, annotate=False):
    """
    Return a function that takes matcher factories and constructs a matcher
    that applies ``function`` to candidate matchees.

    Like ``AfterPreprocessing``, but operates on matcher factories (e.g.
    constructors) rather than matcher objects.

    :param (A -> B) function: Function to apply to matchees before attempting
        to match.
    :param bool annotate: Whether to include a message saying that ``function``
        was applied in the error message.

    :return: New matcher factory.
    :rtype: (*a -> **kw -> Matcher[A]) -> (*args -> **kwargs -> Matcher[B])
    """
    def decorated(matcher):
        def make_matcher(*args, **kwargs):
            return AfterPreprocessing(
                function, matcher(*args, **kwargs), annotate=annotate)

        return make_matcher
    return decorated


def _filepath_to_path(filepath):
    """
    Convert FilePath to a regular path.
    """
    return filepath.path


_on_filepath = after(_filepath_to_path)


path_exists = _on_filepath(PathExists)
"""
Match if a path exists on disk.

For example::

    self.assertThat('/bin/sh', path_exists())

will probably pass on most Unix systems, but::

    self.assertThat('/jml-is-awesome', path_exists())

will most likely fail.
"""


dir_exists = _on_filepath(DirExists)
"""
Match if a directory exists on disk.
"""


file_exists = _on_filepath(FileExists)
"""
Match if a file exists on disk.
"""


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
