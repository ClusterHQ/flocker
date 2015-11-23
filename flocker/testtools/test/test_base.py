"""
Tests for flocker base test cases.
"""

import errno
import os
import shutil
import string
import unittest

from hypothesis import assume, given
from hypothesis.strategies import integers, lists, text
from testtools import PlaceHolder, TestCase, TestResult
from testtools.matchers import (
    AllMatch,
    AfterPreprocessing,
    Annotate,
    Contains,
    DirExists,
    HasLength,
    Equals,
    FileContains,
    Matcher,
    MatchesAny,
    LessThan,
    Not,
    PathExists,
    StartsWith,
)
from twisted.python.filepath import FilePath

from .._base import (
    AsyncTestCase,
    make_temporary_directory,
    _path_for_test_id,
)
from .._testhelpers import (
    has_results,
    only_skips,
    run_test,
)


class AsyncTestCaseTests(TestCase):
    """
    Tests for `AsyncTestCase`.
    """

    @given(text(average_size=30))
    def test_trial_skip_exception(self, reason):
        """
        If tests raise the ``SkipTest`` exported by Trial, then that's
        recorded as a skip.
        """

        class SkippingTest(AsyncTestCase):
            def test_skip(self):
                raise unittest.SkipTest(reason)

        test = SkippingTest('test_skip')
        result = run_test(test)
        self.assertThat(result, only_skips(1, [reason]))

    def test_mktemp_doesnt_exist(self):
        """
        ``mktemp`` returns a path that doesn't exist inside a directory that
        does.
        """

        class SomeTest(AsyncTestCase):
            def test_pass(self):
                pass

        test = SomeTest('test_pass')
        temp_path = FilePath(test.mktemp())
        self.addCleanup(_remove_dir, temp_path.parent())

        self.expectThat(temp_path.parent().path, DirExists())
        self.expectThat(temp_path.path, Not(PathExists()))
        self.assertThat(temp_path, BelowPath(FilePath(os.getcwd())))

    def test_mktemp_not_deleted(self):
        """
        ``mktemp`` returns a path that's not deleted after the test is run.
        """
        created_files = []

        class SomeTest(AsyncTestCase):
            def test_create_file(self):
                path = self.mktemp()
                created_files.append(path)
                open(path, 'w').write('hello')

        run_test(SomeTest('test_create_file'))
        [path] = created_files
        self.addCleanup(os.unlink, path)
        self.assertThat(path, FileContains('hello'))

    def test_run_twice(self):
        """
        Tests can be run twice without errors.

        This is being fixed upstream at
        https://github.com/testing-cabal/testtools/pull/165/, and this test
        coverage is inadequate for a thorough fix. However, this will be
        enough to let us use ``trial -u`` (see FLOC-3462).
        """

        class SomeTest(AsyncTestCase):
            def test_something(self):
                pass

        test = SomeTest('test_something')
        result = TestResult()
        test.run(result)
        test.run(result)
        self.assertThat(
            result, has_results(
                tests_run=Equals(2),
            )
        )


identifier_characters = string.ascii_letters + string.digits + '_'
identifiers = text(average_size=20, min_size=1, alphabet=identifier_characters)
fqpns = lists(
    identifiers, min_size=1, average_size=5).map(lambda xs: '.'.join(xs))
tests = lists(identifiers, min_size=3, average_size=5).map(
    lambda xs: PlaceHolder('.'.join(xs)))


class MakeTemporaryTests(TestCase):
    """
    Tests for code for making temporary files and directories for tests.
    """

    @given(test_id=fqpns, max_length=integers(min_value=1, max_value=64))
    def test_directory_for_test(self, test_id, max_length):
        """
        _path_for_test_id returns a relative path of $module/$class/$method for
        the given test id.
        """
        assume(test_id.count('.') > 1)
        path = _path_for_test_id(test_id, max_length)
        self.expectThat(path, Not(StartsWith('/')))
        segments = path.split('/')
        self.expectThat(segments, HasLength(3))
        self.assertThat(
            segments,
            AllMatch(
                AfterPreprocessing(
                    len, MatchesAny(
                        LessThan(max_length),
                        Equals(max_length)
                    )
                )
            )
        )

    @given(test_id=fqpns)
    def test_too_short_test_id(self, test_id):
        """
        If the given test id is has too few segments, raise an error.
        """
        assume(test_id.count('.') < 2)
        self.assertRaises(ValueError, _path_for_test_id, test_id)

    @given(tests)
    def test_make_temporary_directory(self, test):
        """
        Given a test, make a temporary directory.
        """
        temp_dir = make_temporary_directory(test)
        self.addCleanup(_remove_dir, temp_dir)
        self.expectThat(temp_dir.path, DirExists())
        self.assertThat(temp_dir, BelowPath(FilePath(os.getcwd())))


def _remove_dir(path):
    """
    Safely remove the directory 'path'.
    """
    try:
        shutil.rmtree(path.path)
    except OSError as e:
        if e.errno != errno.ENOENT:
            raise


class BelowPath(Matcher):
    """
    Match if the given path is a child (or grandchild, etc.) of the specified
    parent.
    """

    def __init__(self, parent):
        """
        Construct a ``BelowPath`` that will successfully match for any child
        of ``parent``.

        :param FilePath parent: The parent path. Any path beneath this will
            match.
        """
        self._parent = parent

    def match(self, child):
        """
        Assert ``child`` is beneath the core path.
        """
        return Annotate(
            "%s in not beneath %s" % (child, self._parent),
            Contains(self._parent)).match(child.parents())
