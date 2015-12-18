# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for flocker base test cases.
"""

import errno
import os
import shutil
import string
import unittest

from eliot import MessageType, fields
from hypothesis import assume, given
from hypothesis.strategies import binary, integers, lists, text

# Use testtools' TestCase for most of these tests so that bugs in our base test
# case classes don't invalidate the tests for those classes.
from testtools import TestCase as TesttoolsTestCase
from testtools import PlaceHolder, TestResult
from testtools.matchers import (
    AllMatch,
    AfterPreprocessing,
    Annotate,
    Contains,
    ContainsDict,
    DirExists,
    HasLength,
    EndsWith,
    Equals,
    FileContains,
    Is,
    Matcher,
    MatchesAny,
    MatchesDict,
    MatchesRegex,
    LessThan,
    Not,
    PathExists,
    StartsWith,
)
from twisted.internet.defer import succeed, fail
from twisted.python.filepath import FilePath

from .. import CustomException, AsyncTestCase
from .._base import (
    make_temporary_directory,
    _SplitEliotLogs,
    _get_eliot_data,
    _iter_lines,
    _path_for_test_id,
)
from .._testhelpers import (
    base_test_cases,
    has_results,
    only_skips,
    run_test,
)


class BaseTestCaseTests(TesttoolsTestCase):
    """
    Tests for our base test cases.
    """

    @given(base_test_cases, text(average_size=30))
    def test_trial_skip_exception(self, base_test_case, reason):
        """
        If tests raise the ``SkipTest`` exported by Trial, then that's
        recorded as a skip.
        """

        class SkippingTest(base_test_case):
            def test_skip(self):
                raise unittest.SkipTest(reason)

        test = SkippingTest('test_skip')
        result = run_test(test)
        self.assertThat(result, only_skips(1, [reason]))

    @given(base_test_cases)
    def test_mktemp_doesnt_exist(self, base_test_case):
        """
        ``mktemp`` returns a path that doesn't exist inside a directory that
        does.
        """

        class SomeTest(base_test_case):
            def test_pass(self):
                pass

        test = SomeTest('test_pass')
        temp_path = FilePath(test.mktemp())
        self.addCleanup(_remove_dir, temp_path.parent())

        self.expectThat(temp_path.parent().path, DirExists())
        self.expectThat(temp_path.path, Not(PathExists()))
        self.assertThat(temp_path, BelowPath(FilePath(os.getcwd())))

    @given(base_test_cases)
    def test_mktemp_not_deleted(self, base_test_case):
        """
        ``mktemp`` returns a path that's not deleted after the test is run.
        """
        created_files = []

        class SomeTest(base_test_case):
            def test_create_file(self):
                path = self.mktemp()
                created_files.append(path)
                open(path, 'w').write('hello')

        run_test(SomeTest('test_create_file'))
        [path] = created_files
        self.addCleanup(os.unlink, path)
        self.assertThat(path, FileContains('hello'))

    @given(base_test_cases)
    def test_run_twice(self, base_test_case):
        """
        Tests can be run twice without errors.

        This is being fixed upstream at
        https://github.com/testing-cabal/testtools/pull/165/, and this test
        coverage is inadequate for a thorough fix. However, this will be
        enough to let us use ``trial -u`` (see FLOC-3462).
        """

        class SomeTest(base_test_case):
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

    @given(base_test_cases)
    def test_attaches_twisted_log(self, base_test_case):
        """
        Flocker base test cases attach the Twisted log as a detail.
        """
        class SomeTest(base_test_case):
            def test_something(self):
                from twisted.python import log
                log.msg('foo')

        test = SomeTest('test_something')
        test.run()
        self.assertThat(
            test.getDetails(),
            ContainsDict({
                'twisted-log': match_text_content(MatchesRegex(
                    r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}[+-]\d{4} \[-\] foo$'
                )),
            }))

    @given(base_test_cases)
    def test_separate_eliot_log(self, base_test_case):
        """
        Flocker base test cases attach the eliot log as a detail separate from
        the Twisted log.
        """
        message_type = MessageType(u'foo', fields(name=str), u'test message')

        class SomeTest(base_test_case):
            def test_something(self):
                from twisted.python import log
                log.msg('foo')
                message_type(name='qux').write()

        test = SomeTest('test_something')
        test.run()
        self.assertThat(
            test.getDetails(),
            MatchesDict({
                'twisted-log': match_text_content(MatchesRegex(
                    r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}[+-]\d{4} \[-\] foo$'
                )),
                _SplitEliotLogs._ELIOT_LOG_DETAIL_NAME: match_text_content(
                    Contains("  message_type: 'foo'\n"
                             "  name: 'qux'\n")
                ),
            }))


def match_text_content(matcher):
    """
    Match the text of a ``Content`` instance.
    """
    return AfterPreprocessing(lambda content: content.as_text(), matcher)


class IterLinesTests(TesttoolsTestCase):
    """
    Tests for ``_iter_lines``.
    """

    @given(lists(binary()), binary(min_size=1))
    def test_preserves_data(self, data, separator):
        """
        Splitting into lines loses no data.
        """
        observed = _iter_lines(iter(data), separator)
        self.assertThat(''.join(observed), Equals(''.join(data)))

    @given(lists(binary()), binary(min_size=1))
    def test_separator_terminates(self, data, separator):
        """
        After splitting into lines, each line ends with the separator.
        """
        # Make sure data ends with the separator.
        data.append(separator)
        observed = list(_iter_lines(iter(data), separator))
        self.assertThat(observed, AllMatch(EndsWith(separator)))

    @given(lists(binary(min_size=1), min_size=1), binary(min_size=1))
    def test_nonterminated_line(self, data, separator):
        """
        If the input data does not end with a separator, then every line ends
        with a separator *except* the last line.
        """
        assume(not data[-1].endswith(separator))
        observed = list(_iter_lines(iter(data), separator))
        self.expectThat(observed[:-1], AllMatch(EndsWith(separator)))
        self.assertThat(observed[-1], Not(EndsWith(separator)))


class GetEliotDataTests(TesttoolsTestCase):
    """
    Tests for ``_get_eliot_data``.
    """

    def test_twisted_line(self):
        """
        When given a line logged by Twisted, _get_eliot_data returns ``None``.
        """
        line = '2015-12-11 11:59:48+0000 [-] foo\n'
        self.assertThat(_get_eliot_data(line), Is(None))

    def test_eliot_line(self):
        """
        When given a line logged by Eliot, _get_eliot_data returns the bytes
        that were logged by Eliot.
        """
        logged_line = (
            '2015-12-11 11:59:48+0000 [-] ELIOT: '
            '{"timestamp": 1449835188.575052, '
            '"task_uuid": "6c579710-1b95-4604-b5a1-36b56f8ceb53", '
            '"message_type": "foo", '
            '"name": "qux", '
            '"task_level": [1]}\n'
        )
        expected = (
            '{"timestamp": 1449835188.575052, '
            '"task_uuid": "6c579710-1b95-4604-b5a1-36b56f8ceb53", '
            '"message_type": "foo", '
            '"name": "qux", '
            '"task_level": [1]}'
        )
        self.assertThat(_get_eliot_data(logged_line), Equals(expected))


identifier_characters = string.ascii_letters + string.digits + '_'
identifiers = text(average_size=20, min_size=1, alphabet=identifier_characters)
fqpns = lists(
    identifiers, min_size=1, average_size=5).map(lambda xs: '.'.join(xs))
tests = lists(identifiers, min_size=3, average_size=5).map(
    lambda xs: PlaceHolder('.'.join(xs)))


class MakeTemporaryTests(TesttoolsTestCase):
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


class AssertFailureTests(TesttoolsTestCase):
    """
    Tests for the Twisted-compatibility ``AsyncTestCase.assertFailure`` method.
    """
    def test_success(self):
        """
        ``assertFailure`` fails if the deferred succeeds.
        """

        class Tests(AsyncTestCase):
            def test_success(self):
                return self.assertFailure(succeed(None), ValueError)

        result = run_test(Tests('test_success'))
        self.assertThat(
            result,
            has_results(failures=HasLength(1), tests_run=Equals(1)))

    def test_failure(self):
        """
        ``assertFailure`` returns the exception if the deferred fires with a
        failure.
        """
        class Tests(AsyncTestCase):
            def test_success(self):
                exc = CustomException()
                d = self.assertFailure(fail(exc), type(exc))
                d.addCallback(
                    lambda exception: self.assertThat(exception, Equals(exc))
                )
                return d

        result = run_test(Tests('test_success'))
        self.assertThat(
            result,
            has_results(tests_run=Equals(1)))
