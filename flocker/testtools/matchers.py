# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
testtools matchers used in Flocker tests.
"""

from functools import partial
import os

from pyrsistent import PClass, field, pmap_field
from testtools.content import Content
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
    # XXX: Probably should be part of upstream testtools.
    def decorated(matcher):
        def make_matcher(*args, **kwargs):
            return AfterPreprocessing(
                function, matcher(*args, **kwargs), annotate=annotate)

        return make_matcher
    return decorated


class _Mismatch(PClass):
    """
    Immutable Mismatch that also stores the mismatched object.

    :ivar mismatched: The object that failed to match.
    """

    # XXX: No direct tests.

    # XXX: jml thinks the base testtools mismatch should be extended to
    # include the mismatched object.

    mismatched = field(object)
    _description = field((str, unicode))
    _details = pmap_field((str, unicode), Content)

    def describe(self):
        return self._description

    def get_details(self):
        return self._details


def mismatch(mismatched, description, details):
    """
    Create an immutable Mismatch that also stores the mismatched object.
    """
    return _Mismatch(
        mismatched=mismatched, _description=description, _details=details)


def _adapt_mismatch(original, matchee):
    """
    If ``original`` doesn't already store ``matchee`` then return a new
    one that has it stored.
    """
    # XXX: No direct tests.
    marker = object()
    if getattr(original, 'mismatched', marker) is marker:
        return mismatch(matchee, original.describe(), original.get_details())
    return original


class _OnMismatch(PClass):
    """
    Decorate a matcher with a function that is run on mismatch.
    """

    _function = field()
    _matcher = field()

    def match(self, matchee):
        """
        Match if ``matchee`` matches the wrapped matcher.

        If it does not match, apply the given function to the mismatch, first
        ensuring that the mismatch has ``mismatched`` set.
        """
        mismatch = self._matcher.match(matchee)
        if mismatch is None:
            return
        return self._function(_adapt_mismatch(mismatch, matchee))


def OnMismatch(function, matcher):
    """
    Decorate ``matcher`` such that ``function`` is called on mismatches.
    """
    return _OnMismatch(_function=function, _matcher=matcher)


def on_mismatch(function):
    """
    Return a function that maps matcher factories to new matcher factories,
    such that the matchers returned by the new factories have ``function``
    applied to any mismatch they receive.

    :param (_Mismatch[A] -> _Mismatch[B]) function: Applied to any mismatch.
    :return: A function that operates on matcher factories.
    """
    def decorated(matcher):
        def make_matcher(*args, **kwargs):
            return _OnMismatch(function, matcher(*args, **kwargs))

        return make_matcher
    return decorated


def _filepath_to_path(filepath):
    """
    Convert FilePath to a regular path.
    """
    return filepath.path


_on_filepath = after(_filepath_to_path)
"""
Lift regular path matchers to be FilePath matchers.
"""


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


def file_contents(matcher):
    """
    Match if a file's contents match ``matcher``.

    For example::

        self.assertThat(
            FilePath('/foo/bar/baz'),
            file_contents(Equals('hello world')))

    Will match if there is a file ``/foo/bar/baz`` and if its contents are
    exactly ``hello world``.
    """

    def get_content(file_path):
        return file_path.getContent()

    def content_mismatches(original):
        return mismatch(
            original.mismatched,
            '%s has unexpected contents:\n%s' % (
                original.mismatched.path, original.describe()),
            original.get_details(),
        )
    # We don't use ``FileContains``, as that raises an IOError if the path is
    # for an existing directory.
    return MatchesAll(
        file_exists(),
        OnMismatch(
            content_mismatches,
            AfterPreprocessing(get_content, matcher, annotate=False)),
        first_only=True,
    )


with_permissions = partial(
    AfterPreprocessing,
    lambda filepath: os.stat(filepath.path).st_mode & 07777)
"""
Match if path has the given permissions.
"""
