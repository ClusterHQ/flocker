# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Base classes for unit tests.
"""

from datetime import timedelta
from functools import partial
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


class TestCase(unittest.SynchronousTestCase):
    """
    Base class for synchronous test cases.
    """


def async_runner(timeout, flaky_output=None):
    """
    Make a ``RunTest`` instance for asynchronous tests.

    :param timedelta timeout: The maximum length of time that a test is allowed
        to take.
    :param file flaky_output: A file-like object to which we'll send output
        about flaky tests. This is a temporary measure until we fix FLOC-3469,
        at which point we will just use standard logging.
    """
    if flaky_output is None:
        flaky_output = sys.stdout
    # XXX: Looks like the acceptance tests (which were the first tests that we
    # tried to migrate) aren't cleaning up after themselves even in the
    # successful case. Use AsynchronousDeferredRunTestForBrokenTwisted, which
    # loops the reactor a couple of times after the test is done.
    return retry_flaky(
        AsynchronousDeferredRunTestForBrokenTwisted.make_factory(
            timeout=timeout.total_seconds(),
            suppress_twisted_logging=False,
            store_twisted_logs=False,
        ),
        output=flaky_output,
    )


# By default, asynchronous tests are timed out after 2 minutes.
DEFAULT_ASYNC_TIMEOUT = timedelta(minutes=2)


def _test_skipped(case, result, exception):
    result.addSkip(case, details={'reason': text_content(unicode(exception))})


class AsyncTestCase(testtools.TestCase):
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
        # Need the cleanups in this to run *after* the cleanup in
        # CaptureTwistedLogs, so add it first, because cleanups are run in
        # reverse order.
        #
        # Would ideally like to have all the log capturing (including
        # post-processing) in its own fixture that wraps up
        # CaptureTwistedLogs, but there doesn't seem to be a way to do that.
        # https://github.com/testing-cabal/fixtures/pull/20 for details.
        #
        # XXX: Would also be useful for synchronous test cases once they're
        # migrated over to testtools.
        self.useFixture(_SplitEliotLogs(self))
        self.useFixture(CaptureTwistedLogs())

    def mktemp(self):
        """
        Create a temporary directory that will be deleted on test completion.

        Provided for compatibility with Twisted's ``TestCase``.

        :return: Path to the newly-created temporary directory.
        """
        # XXX: Should we provide a cleaner interface for people to use? One
        # that returns FilePath? One that returns a directory?

        # XXX: Actually belongs in a mixin or something, not actually specific
        # to async.
        return make_temporary_directory(self).child('temp').path


class _SplitEliotLogs(Fixture):
    """
    Split the Eliot logs out of Twisted logs.

    Assumes that Twisted logs contain Eliot logs as per
    ``flocker._redirect_eliot_logs_for_trial``, and that these logs have been
    attached to a test case as a detail named with the value of
    ``CaptureTwistedLogs.LOG_DETAIL_NAME``.

    Takes the Eliot logs that are in the Trial logs and splits them into a
    separate detail that contains only the pretty printed Eliot logs.
    """

    _ELIOT_LOG_DETAIL_NAME = 'twisted-eliot-log'

    def __init__(self, case):
        super(_SplitEliotLogs, self).__init__()
        self._case = case

    def _setUp(self):
        self.addCleanup(self._post_process_twisted_logs, self._case)

    def _post_process_twisted_logs(self, case):
        """
        Split the eliot logs out of the Twisted logs.

        :param TestCase case: The test case to which the Twisted log details
            were attached.
        """
        # XXX: Mutating the details dict of the TestCase is a bit of a hack.
        # See comment in AsyncTestCase.setUp for explanation.
        twisted_log = case.getDetails().pop(CaptureTwistedLogs.LOG_DETAIL_NAME)
        new_twisted_log, eliot_log = _fix_twisted_logs(twisted_log)
        # Overrides the existing Twisted log.
        case.addDetail(CaptureTwistedLogs.LOG_DETAIL_NAME, new_twisted_log)
        case.addDetail(self._ELIOT_LOG_DETAIL_NAME, eliot_log)


def _fix_twisted_logs(log_content):
    """
    Split the Eliot logs out of a Twisted log.

    :param Content log_content: A text content object that contains a Twisted
        log.
    :return: The log split into two, the first containing the core Twisted log
        messages and the second containing line-separated Eliot JSON messages.
    :rtype: (Content, Content)
    """
    twisted_lines, eliot_lines = _split_map_maybe(
        _get_eliot_data, _iter_content_lines(log_content))
    return (
        Content(UTF8_TEXT, lambda: twisted_lines),
        Content(UTF8_TEXT, partial(_prettyformat_lines, eliot_lines)),
    )


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
_ELIOT_MARKER_LENGTH = len(_ELIOT_MARKER)


def _get_eliot_data(twisted_log_line):
    """
    Given a line from a Twisted log message, return the text of the Eliot log
    message that is on that line.

    If there is no Eliot message on that line, return ``None``.

    :return: A logged eliot message without Twisted logging preamble, or
        ``None``.
    :rtype: unicode or ``NoneType``.
    """
    index = twisted_log_line.find(_ELIOT_MARKER)
    if index < 0:
        return None
    return twisted_log_line[index + _ELIOT_MARKER_LENGTH:].strip()


def _iter_content_lines(content):
    """
    Iterate over the lines that make up ``content``.

    :param Content content: Arbitrary newline-separated content.
    :yield: Newline-terminated bytestrings that make up the content.
    """
    return _iter_lines(content.iter_bytes(), '\n')


def _iter_lines(byte_iter, separator='\n'):
    """
    Iterate over the lines that make up ``content``.

    :param iter(bytes) byte_iter: An iterable of bytes.
    :param bytes separator: A single byte that marks the end of a line.
    :yield: Separator-terminated bytestrings.
    """
    # XXX: Someone must have written this before.
    # XXX: Move this to flocker.common?
    chunks = []
    for data in byte_iter:
        while data:
            index = data.find(separator)
            if index < 0:
                chunks.append(data)
                break

            head, data = data[:index + 1], data[index + 1:]
            chunks.append(head)
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
