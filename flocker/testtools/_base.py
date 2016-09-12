# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Base classes for unit tests.
"""

from datetime import timedelta
from itertools import tee
import json
import tempfile
from unittest import SkipTest

from eliot.prettyprint import pretty_format
from fixtures import Fixture
import testtools
from testtools.content import Content, text_content
from testtools.content_type import UTF8_TEXT
from testtools.twistedsupport import (
    AsynchronousDeferredRunTestForBrokenTwisted, assert_fails_with,
    CaptureTwistedLogs,
)

from twisted.python import log
from twisted.python.filepath import FilePath
from twisted.trial import unittest

from ..common import make_file
from ._flaky import retry_flaky


class _MktempMixin(object):
    """
    ``mktemp`` support for testtools TestCases.
    """

    def mktemp(self):
        """
        Create a temporary path for use in tests.

        Provided for compatibility with Twisted's ``TestCase``.

        :return: Path to non-existent file or directory.
        """
        return self.make_temporary_path().path

    def make_temporary_path(self):
        """
        Create a temporary path for use in tests.

        :return: Path to non-existent file or directory.
        :rtype: FilePath
        """
        return self.make_temporary_directory().child('temp')

    def make_temporary_directory(self):
        """
        Create a temporary directory for use in tests.

        :return: Path to directory.
        :rtype: FilePath
        """
        return make_temporary_directory(_path_for_test(self))

    def make_temporary_file(self, content='', permissions=None):
        """
        Create a temporary file for use in tests.

        :param str content: Content to write to the file.
        :param int permissions: The permissions for the file
        :return: Path to file.
        :rtype: FilePath
        """
        return make_file(self.make_temporary_path(), content, permissions)


class _DeferredAssertionMixin(object):
    """
    Synchronous Deferred-related assertions support for testtools TestCase.

    This is provided for compatibility with Twisted's TestCase.  New code
    should use matchers instead.
    """
    successResultOf = unittest.SynchronousTestCase.successResultOf.__func__
    failureResultOf = unittest.SynchronousTestCase.failureResultOf.__func__
    assertNoResult = unittest.SynchronousTestCase.assertNoResult.__func__

    # Not related to Deferreds but required by the implementation of the above.
    assertIdentical = unittest.SynchronousTestCase.assertIdentical.__func__


class TestCase(testtools.TestCase, _MktempMixin, _DeferredAssertionMixin):
    """
    Base class for synchronous test cases.
    """

    run_tests_with = retry_flaky(testtools.RunTest)
    # Eliot's validateLogging hard-codes a check for SkipTest when deciding
    # whether to check for valid logging, which is fair enough, since there's
    # no other API for checking whether a test has skipped. Setting
    # skipException tells testtools to treat unittest.SkipTest as the
    # exception that signals skipping.
    skipException = SkipTest

    def setUp(self):
        log.msg("--> Begin: %s <--" % (self.id()))
        super(TestCase, self).setUp()
        self.useFixture(_SplitEliotLogs())


class _AsyncRunner(AsynchronousDeferredRunTestForBrokenTwisted):
    """
    Runner for asynchronous tests.

    Extends base functionality to correctly capture logs for failed tests.
    """

    def _get_log_fixture(self):
        """Return a fixture used to capture logs."""
        # XXX: This is a hack, relying on the internal implementation details
        # of AsynchronousDeferredRunTest.
        #
        # We want to use the _SplitEliotLogs fixture, but we want to make sure
        # that it's set up & torn down *outside* the test itself.
        # Specifically, outside the Spinner.run call method that's in
        # _run_core.
        #
        # Because there are no hooks provided for this (although maybe there
        # should be), we're going to use what's available to us. The return
        # value of _get_log_fixture is used outside the Spinner run loop, and
        # its details gathered.
        return _SplitEliotLogs()

    def _run_core(self):
        """Template method that actually runs the suite."""
        # Record the log starter *before* we run core, so that the
        # _SplitEliotLogs fixture doesn't include it.
        log.msg("--> Begin: %s <--" % (self.case.id()))
        super(_AsyncRunner, self)._run_core()


def async_runner(timeout):
    """
    Make a ``RunTest`` instance for asynchronous tests.

    :param timedelta timeout: The maximum length of time that a test is allowed
        to take.
    """
    # XXX: The acceptance tests (which were the first tests that we tried to
    # migrate) aren't cleaning up after themselves even in the successful
    # case. Use AsynchronousDeferredRunTestForBrokenTwisted, which loops the
    # reactor a couple of times after the test is done.
    async_factory = _AsyncRunner.make_factory(
        timeout=timeout.total_seconds(),
        suppress_twisted_logging=False,
        store_twisted_logs=False,
    )
    return retry_flaky(async_factory)


# By default, asynchronous tests are timed out after 2 minutes.
DEFAULT_ASYNC_TIMEOUT = timedelta(minutes=2)


def _test_skipped(case, result, exception):
    result.addSkip(case, details={'reason': text_content(unicode(exception))})


class AsyncTestCase(testtools.TestCase, _MktempMixin, _DeferredAssertionMixin):
    """
    Base class for asynchronous test cases.

    :ivar reactor: The Twisted reactor that the test is being run in. Set by
        ``async_runner`` and only available for the duration of the test.
    """

    run_tests_with = async_runner(timeout=DEFAULT_ASYNC_TIMEOUT)
    # See comment on TestCase.skipException.
    skipException = SkipTest

    def assertFailure(self, deferred, exception):
        """
        ``twisted.trial.unittest.TestCase.assertFailure``-alike.

        This is not completely compatible.  ``assert_fails_with`` should be
        preferred for new code.
        """
        return assert_fails_with(deferred, exception)


class _SplitEliotLogs(Fixture):
    """
    Split the Eliot logs out of Twisted logs.

    Captures Twisted logs that contain Eliot logs as per
    ``flocker._redirect_eliot_logs_for_trial``, and ensures these logs are
    attached to a test case as details: one that contains the pure Twisted
    logs without Eliot logs, and one that contains only the pretty printed
    Eliot logs.
    """

    _ELIOT_LOG_DETAIL_NAME = 'twisted-eliot-log'

    def _setUp(self):
        twisted_logs = self.useFixture(CaptureTwistedLogs())
        self._fix_twisted_logs(twisted_logs, twisted_logs.LOG_DETAIL_NAME)

    def _fix_twisted_logs(self, detailed, detail_name):
        """
        Split the Eliot logs out of a Twisted log.

        :param detailed: Object with ``getDetails`` where the original Twisted
            logs are stored.
        :param detail_name: Name of the Twisted log detail.
        """
        twisted_log = detailed.getDetails()[detail_name]
        split_logs = [None]

        def _get_split_logs():
            # Memoize the split log so we don't iterate through it twice.
            if split_logs[0] is None:
                split_logs[0] = _split_map_maybe(
                    extract_eliot_from_twisted_log,
                    _iter_content_lines(twisted_log),
                )
            return split_logs[0]

        # The trick here is that we can't iterate over the base detail yet.
        # We can only use it inside the iter_bytes of the Content objects
        # that we add. This is because the only time that we *know* the
        # details are populated is when the details are evaluated. If we call
        # it in _setUp(), the logs are empty. If we call it in cleanup, the
        # detail is gone.

        detailed.addDetail(
            detail_name,
            Content(UTF8_TEXT, lambda: _get_split_logs()[0]))

        detailed.addDetail(
            self._ELIOT_LOG_DETAIL_NAME,
            Content(
                UTF8_TEXT, lambda: _prettyformat_lines(_get_split_logs()[1])))


def _split_map_maybe(function, sequence, marker=None):
    """
    Lazily map ``function`` over ``sequence``, yielding two streams:
    ``(original, applied)``

    :param function: Unary callable that might return ``marker``.
    :param sequence: Iterable of objects that ``function`` will be applied to.
    :param marker: Value returned by ``function`` when it cannot be
        meaningfully applied to an object in ``sequence``.
    :return: ``(original, applied)``, where ``original`` is an iterable of all
        the elements, ``x``, in ``sequence`` where ``function(x)`` is
        ``marker``, and ``applied`` is an iterable of all of the results of
        ``function(x)`` that are not ``marker``.
    """
    annotated = ((x, function(x)) for x in sequence)
    original, mapped = tee(annotated)
    return (
        (x for (x, y) in original if y is marker),
        (y for (x, y) in mapped if y is not marker)
    )


def _prettyformat_lines(lines):
    """
    Pretty format lines of Eliot logs.
    """
    for line in lines:
        data = json.loads(line)
        yield pretty_format(data) + '\n'


def extract_eliot_from_twisted_log(twisted_log_line):
    """
    Given a line from a Twisted log message, return the text of the Eliot log
    message that is on that line.

    If there is no Eliot message on that line, return ``None``.

    :param str twisted_log_line: A line from a Twisted test.log.
    :return: A logged eliot message without Twisted logging preamble, or
        ``None``.
    :rtype: unicode or ``NoneType``.
    """
    open_brace = twisted_log_line.find('{')
    close_brace = twisted_log_line.rfind('}')
    if open_brace == -1 or close_brace == -1:
        return None
    candidate = twisted_log_line[open_brace:close_brace + 1]
    try:
        fields = json.loads(candidate)
    except (ValueError, TypeError):
        return None
    # Eliot lines always have these two keys.
    if {"task_uuid", "timestamp"}.difference(fields):
        return None
    return candidate


def _iter_content_lines(content):
    """
    Iterate over the lines that make up ``content``.

    :param Content content: Arbitrary newline-separated content.
    :yield: Newline-terminated bytestrings that make up the content.
    """
    return _iter_lines(content.iter_bytes(), '\n')


def _iter_lines(byte_iter, line_separator):
    """
    Iterate over the lines that make up ``content``.

    :param iter(bytes) byte_iter: An iterable of bytes.
    :param bytes line_separator: The bytes that mark the end of a line.
    :yield: Separator-terminated bytestrings.
    """
    # XXX: Someone must have written this before.
    # XXX: Move this to flocker.common?
    chunks = []
    for data in byte_iter:
        while data:
            head, sep, data = data.partition(line_separator)
            if not sep:
                chunks.append(head)
                break

            chunks.append(head + sep)
            yield ''.join(chunks)
            chunks = []

    if chunks:
        yield ''.join(chunks)


def _path_for_test_id(test_id, max_segment_length=32):
    """
    Get the temporary directory path for a test ID.

    :param str test_id: A fully-qualified Python name. Must
        have at least three components.
    :param int max_segment_length: The longest that a path segment may be.
    :return: A relative path to ``$module/$class/$method``.
    """
    if test_id.count('.') < 2:
        raise ValueError(
            "Must have at least three components (e.g. foo.bar.baz), got: %r"
            % (test_id,))
    return '/'.join(
        segment[:max_segment_length] for segment in test_id.rsplit('.', 2))


def _path_for_test(test):
    """
    Get the temporary directory path for a test.
    """
    return FilePath(_path_for_test_id(test.id()))


def make_temporary_directory(base_path):
    """
    Create a temporary directory beneath ``base_path``.

    It is the responsibility of the caller to delete the temporary directory.

    :param FilePath base_path: Base directory for the temporary directory.
        Will be created if it does not exist.
    :return: The FilePath to a newly-created temporary directory, created
        beneath the current working directory.
    """
    if not base_path.exists():
        base_path.makedirs()
    temp_dir = tempfile.mkdtemp(dir=base_path.path)
    return FilePath(temp_dir)
