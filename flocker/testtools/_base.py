# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Base classes for unit tests.
"""

from datetime import timedelta
from functools import partial
from itertools import tee
import sys
import tempfile

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
        # Need this to run _after_ the clean-up in CaptureTwistedLogs.
        self.addCleanup(self._post_process_twisted_logs)
        self.useFixture(CaptureTwistedLogs())

    def _post_process_twisted_logs(self):
        """
        Split the eliot logs out of the Twisted logs.
        """
        twisted_log = self.getDetails()['twisted-log']
        new_twisted_log, eliot_log = _fix_twisted_logs(twisted_log)
        # Overrides the existing Twisted log.
        self.addDetail('twisted-log', new_twisted_log)
        self.addDetail('eliot-log', eliot_log)

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


def _fix_twisted_logs(log_content):
    """
    Split the Eliot logs out of a Twisted log.

    :param Content log_content: A text content object that contains a Twisted
        log.
    :return: The log split into two, the first containing the core Twisted log
        messages and the second containing line-separated Eliot JSON messages.
    :rtype: (Content, Content)
    """
    twisted_lines, eliot_lines = tee(_iter_content_lines(log_content))
    return (
        Content(UTF8_TEXT, partial(_pure_twisted_logs, twisted_lines)),
        Content(UTF8_TEXT, partial(_iter_eliot_logs, eliot_lines)),
    )


def _pure_twisted_logs(log_lines):
    """
    Given an iterable of lines of bytes of Twisted logs, yield the lines that
    are not Eliot data.
    """
    return (line for line in log_lines if _get_eliot_data(line) is None)


def _iter_eliot_logs(log_lines):
    """
    Given an iterable of lines of bytes of Twisted logs, yield the Eliot data
    from lines that were logged by Eliot.
    """
    for line in log_lines:
        data = _get_eliot_data(line)
        if data is not None:
            yield data


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

    :param Content content: Text content.
    :raise ValueError: If content is not text content.
    :yield: Newline-terminated UTF8-encoded bytestrings that make up content.
    """
    # XXX: Make this lazy.
    return (line.encode('utf8') for line in content.as_text().splitlines(True))


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
