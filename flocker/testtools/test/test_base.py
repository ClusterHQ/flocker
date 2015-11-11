"""
Tests for flocker base test cases.
"""

import errno
from itertools import chain
import json
import shutil

from eliot import MessageType, fields
from hypothesis import given
from hypothesis.strategies import binary, lists
from testtools import TestCase
from testtools.content import text_content
from testtools.matchers import (
    AfterPreprocessing,
    AllMatch,
    Contains,
    ContainsDict,
    DirExists,
    EndsWith,
    Equals,
    HasLength,
    Matcher,
    MatchesListwise,
    Mismatch,
    Not,
    PathExists,
)
from testtools.testresult.doubles import Python27TestResult
from twisted.python.filepath import FilePath
from twisted.python import log
from twisted.trial import unittest

from .._base import (
    AsyncTestCase,
    _filter_eliot_logs,
)


class AsyncTestCaseTests(TestCase):

    @given(binary())
    def test_trial_skip_exception(self, reason):
        """
        If tests raise the ``SkipTest`` exported by Trial, then that's
        recorded as a skip.
        """

        class SkippingTest(AsyncTestCase):
            def test_skip(self):
                raise unittest.SkipTest(reason)

        test = SkippingTest('test_skip')
        result = Python27TestResult()
        test.run(result)
        self.assertEqual([
            ('startTest', test),
            ('addSkip', test, reason),
            ('stopTest', test),
        ], result._events)

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
        self.assertThat(temp_path.path, Not(PathExists()))

    def test_logs_processed(self):
        """
        We separate the eliot logs out from the Twisted logs when we report.
        """

        ELIOT_MESSAGE = MessageType(
            self.id().replace('.', ':'),
            fields(msg=str),
            u'Message for test_logs_processed')

        class LoggingTest(AsyncTestCase):
            def test_log(self):
                log.msg('twisted log message')
                ELIOT_MESSAGE(msg='eliot message').write()

        test = LoggingTest('test_log')
        test.run(Python27TestResult())

        details = test.getDetails()
        self.assertThat(
            [details.get('twisted-log', text_content('')).as_text(),
             details.get('twisted-eliot-log', text_content('{}')).as_text()],
            MatchesListwise([
                EndsWith('twisted log message\n'),
                EndsWith('msg: eliot message\n'),
            ])
        )


class FilterEliotLogTests(TestCase):
    """
    Tests for ``_filter_eliot_logs``.
    """

    def test_no_eliot_logs(self):
        """
        If there are no Eliot logs, everything is returned in core logs and
        nothing in eliot logs.
        """
        lines = [
            'foo',
            'bar',
            'baz',
        ]
        core_logs, eliot_logs = _filter_eliot_logs(lines)
        self.expectThat(list(core_logs), Equals(lines))
        self.assertThat(list(eliot_logs), Equals([]))

    def test_only_eliot_logs(self):
        """
        If there are only Eliot logs, nothing is returned in core logs and
        everything in eliot logs.
        """
        lines = [
            'ELIOT: foo',
            'prefix ELIOT: bar',
            'ELIOT: baz',
        ]
        core_logs, eliot_logs = _filter_eliot_logs(lines)
        self.expectThat(list(core_logs), Equals([]))
        self.assertThat(list(eliot_logs), Equals(['foo', 'bar', 'baz']))

    @given(lines=lists(binary()), marker=binary(min_size=1, average_size=5))
    def test_marker_not_in_core_logs(self, lines, marker):
        core_logs, _eliot_logs = _filter_eliot_logs(lines, marker)
        self.assertThat(core_logs, AllMatch(Not(Contains(marker))))

    @given(lines=lists(binary()), marker=binary(min_size=1, average_size=5))
    def test_same_lines(self, lines, marker):
        core_logs, eliot_logs = _filter_eliot_logs(lines, marker)
        self.assertThat(
            list(chain(core_logs, eliot_logs)), HasLength(len(lines)))

    @given(lines=lists(binary()), marker=binary(min_size=1, average_size=5))
    def test_core_logs_preserve_order(self, lines, marker):
        core_logs, _eliot_logs = _filter_eliot_logs(lines, marker)
        self.assertThat(core_logs, FoundInOrder(lines))


def _remove_dir(path):
    """
    Safely remove the directory 'path'.
    """
    try:
        shutil.rmtree(path.path)
    except OSError as e:
        if e.errno != errno.ENOENT:
            raise


class FoundInOrder(Matcher):
    """
    Match a sequence if all of the elements appear in the source sequence in
    the same order, albeit not contiguously.
    """

    def __init__(self, source):
        """
        Construct a ``FoundInOrder`` matcher.

        :param iterable source: A larger sequence that contains the definitive
            ordering for a smaller non-contiguous subsequence.
        """
        self._source = list(source)

    def match(self, target):
        """
        Match ``target`` if all its elements appear in the source sequence in
        the order that they appear in the source sequence.

        :return: ``None`` if they do match, ``Mismatch`` if they don't.
        """
        position = 0
        for element in target:
            try:
                position = self._source.index(element, position) + 1
            except ValueError:
                return Mismatch(
                    '{} does not appear in order in {}: {} not found'.format(
                        target, self._source, element))
