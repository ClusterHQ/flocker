# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Base classes for unit tests.
"""

from datetime import timedelta
import tempfile

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

    :param timedelta timeout: The maximum length of time that a test is allowed
        to take.
    """
    # XXX: Looks like the acceptance tests (which were the first tests that we
    # tried to migrate) aren't cleaning up after themselves even in the
    # successful case. Use the RunTest that loops the reactor a couple of
    # times after the test is done.
    return AsynchronousDeferredRunTestForBrokenTwisted.make_factory(
        timeout=timeout.total_seconds())


# By default, asynchronous tests are timed out after 2 minutes.
DEFAULT_ASYNC_TIMEOUT = timedelta(minutes=2)


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
        return make_temporary_directory(self).child('temp').path


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
