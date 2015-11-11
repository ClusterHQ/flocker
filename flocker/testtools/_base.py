# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Base classes for unit tests.
"""

from itertools import tee

import fixtures
import testtools
from testtools.deferredruntest import (
    AsynchronousDeferredRunTestForBrokenTwisted)

from twisted.python.filepath import FilePath
from twisted.trial import unittest


class TestCase(unittest.SynchronousTestCase):
    """
    Base class for synchronous test cases.
    """


def async_runner(timeout):
    """
    Make a ``RunTest`` instance for asynchronous tests.

    :param float timeout: The maximum length of time (in seconds) that a test
        is allowed to take.
    """
    # XXX: Looks like the acceptance tests (which were the first tests that we
    # tried to migrate) aren't cleaning up after themselves even in the
    # successful case. Use the RunTest that loops the reactor a couple of
    # times after the test is done.
    return AsynchronousDeferredRunTestForBrokenTwisted.make_factory(
        timeout=timeout)


# By default, asynchronous tests are timed out after 2 minutes.
DEFAULT_ASYNC_TIMEOUT = 120


def _test_skipped(case, result, exception):
    result.addSkip(case, str(exception))


class AsyncTestCase(testtools.TestCase):
    """
    Base class for asynchronous test cases.
    """

    run_tests_with = async_runner(timeout=DEFAULT_ASYNC_TIMEOUT)

    def __init__(self, *args, **kwargs):
        super(AsyncTestCase, self).__init__(*args, **kwargs)
        self.exception_handlers.insert(-1, (unittest.SkipTest, _test_skipped))

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
        temp_dir = FilePath(self.useFixture(fixtures.TempDir()).path)
        filename = self.id().split('.')[-1][:32]
        return temp_dir.child(filename).path


def _filter_eliot_logs(twisted_log_lines, eliot_token='ELIOT: '):
    """
    Take an iterable of Twisted log lines and return two iterables: one that
    has *only* the regular logs, and one that has only the eliot logs, with
    Twisted stuff stripped off.

    :param iterable twisted_log_lines: An iterable of Twisted log lines.
    :param str eliot_token: The string token that marks a log entry as being
        of eliot.
    :return: A 2-tuple of ``(core_logs, eliot_logs)``, where ``core_logs`` only
        has Twisted core logs, and ``eliot_logs`` has only eliot logs.
    """
    core_logs, eliot_logs = tee(twisted_log_lines)
    eliot_token_len = len(eliot_token)
    return (
        (line for line in core_logs if eliot_token not in line),
        (line[line.index(eliot_token) + eliot_token_len:]
         for line in eliot_logs if eliot_token in line)
    )
