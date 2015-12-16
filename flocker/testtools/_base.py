# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Base classes for unit tests.
"""

from datetime import timedelta
from itertools import tee
import json
import sys
import tempfile

from eliot.prettyprint import pretty_format
from fixtures import Fixture
import testtools
from testtools.content import Content, text_content
from testtools.content_type import UTF8_TEXT
from testtools.deferredruntest import (
    AsynchronousDeferredRunTestForBrokenTwisted,
)

try:
    from testtools.deferredruntest import CaptureTwistedLogs
except ImportError:
    # We are using a fork of testtools, which unfortunately means that we need
    # to do special things to make sure we're using the latest version. Raise
    # an error message that will help people figure out what they need to do.
    raise Exception(
        'Cannot import CaptureTwistedLogs. Maybe upgrade your version of '
        'testtools: pip install --upgrade --process-dependency-links .[dev]'
    )


from twisted.python.filepath import FilePath
from twisted.trial import unittest

from ._flaky import retry_flaky


class _MktempMixin(object):
    """
    ``mktemp`` support for testtools TestCases.
    """

    def mktemp(self):
        """
        Create a temporary directory that will be deleted on test completion.

        Provided for compatibility with Twisted's ``TestCase``.

        :return: Path to the newly-created temporary directory.
        """
        # XXX: Should we provide a cleaner interface for people to use? One
        # that returns FilePath? One that returns a directory?
        return make_temporary_directory(self).child('temp').path


def _retry_runner(runner_factory, flaky_output=None):
    """
    Take a standard testtools RunFactory and make it retry @flaky tests.

    :param runner_factory: A RunTest factory.
    :param file flaky_output: A file-like object to which we'll send output
        about flaky tests. This is a temporary measure until we fix FLOC-3469,
        at which point we will just use standard logging.
    """
    if flaky_output is None:
        flaky_output = sys.stdout
    return retry_flaky(runner_factory, output=flaky_output)


class TestCase(testtools.TestCase, _MktempMixin):
    """
    Base class for synchronous test cases.
    """

    run_tests_with = _retry_runner(testtools.RunTest)

    def __init__(self, *args, **kwargs):
        super(TestCase, self).__init__(*args, **kwargs)
        # XXX: Work around testing-cabal/unittest-ext#60
        self.exception_handlers.insert(-1, (unittest.SkipTest, _test_skipped))

    def setUp(self):
        super(TestCase, self).setUp()
        self.useFixture(_SplitEliotLogs())


def async_runner(timeout, flaky_output=None):
    """
    Make a ``RunTest`` instance for asynchronous tests.

    :param timedelta timeout: The maximum length of time that a test is allowed
        to take.
    :param file flaky_output: A file-like object to which we'll send output
        about flaky tests. This is a temporary measure until we fix FLOC-3469,
        at which point we will just use standard logging.
    """
    # XXX: The acceptance tests (which were the first tests that we tried to
    # migrate) aren't cleaning up after themselves even in the successful
    # case. Use AsynchronousDeferredRunTestForBrokenTwisted, which loops the
    # reactor a couple of times after the test is done.
    async_factory = AsynchronousDeferredRunTestForBrokenTwisted.make_factory(
        timeout=timeout.total_seconds(),
        suppress_twisted_logging=False,
        store_twisted_logs=False,
    )
    return _retry_runner(async_factory, flaky_output)


# By default, asynchronous tests are timed out after 2 minutes.
DEFAULT_ASYNC_TIMEOUT = timedelta(minutes=2)


def _test_skipped(case, result, exception):
    result.addSkip(case, details={'reason': text_content(unicode(exception))})


class AsyncTestCase(testtools.TestCase, _MktempMixin):
    """
    Base class for asynchronous test cases.
    """

    run_tests_with = async_runner(timeout=DEFAULT_ASYNC_TIMEOUT)

    def __init__(self, *args, **kwargs):
        super(AsyncTestCase, self).__init__(*args, **kwargs)
        # XXX: Work around testing-cabal/unittest-ext#60
        self.exception_handlers.insert(-1, (unittest.SkipTest, _test_skipped))

    def setUp(self):
        super(AsyncTestCase, self).setUp()
        self.useFixture(_SplitEliotLogs())


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
                    _get_eliot_data, _iter_content_lines(twisted_log),
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


_ELIOT_MARKER = ' [-] ELIOT: '


def _get_eliot_data(twisted_log_line):
    """
    Given a line from a Twisted log message, return the text of the Eliot log
    message that is on that line.

    If there is no Eliot message on that line, return ``None``.

    :return: A logged eliot message without Twisted logging preamble, or
        ``None``.
    :rtype: unicode or ``NoneType``.
    """
    _, _, eliot_data = twisted_log_line.partition(_ELIOT_MARKER)
    if eliot_data:
        return eliot_data.strip()


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


def make_temporary_directory(test):
    """
    Create a temporary directory for use in ``test``.

    :param TestCase test: A TestCase
    :return: The FilePath to a newly-created temporary directory, created
        beneath the current working directory.
    """
    path = FilePath(_path_for_test_id(test.id()))
    if not path.exists():
        path.makedirs()
    temp_dir = tempfile.mkdtemp(dir=path.path)
    return FilePath(temp_dir)
