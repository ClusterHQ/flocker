# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Logic for handling flaky tests.
"""

from functools import wraps

import testtools


def flaky(jira_key):
    """
    Mark a test as flaky.

    A 'flaky' test is one that sometimes passes but sometimes fails. Marking a
    test as flaky means both failures and successes are expected, and that
    neither will fail the test run.

    :param unicode jira_key: The JIRA key of the bug for this flaky test,
        e.g. 'FLOC-2345'
    :return: A decorator that can be applied to `TestCase` methods.
    """
    # XXX: This raises a crappy error message if you forgot to provide a JIRA
    # key. Is there a way to provide a good one?

    # TODO (see FLOC-3281):
    # - allow specifying which exceptions are expected
    # - retry on expected exceptions
    #   - parametrize on retry options
    # - provide interesting & parseable logs for flaky tests

    def wrapper(test_method):
        return test_method
    return wrapper


class _RetryFlaky(object):
    """
    ``RunTest`` implementation that retries tests that fail.
    """

    # XXX: This should probably become a part of testtools:
    # https://bugs.launchpad.net/testtools/+bug/1515933

    def __init__(self, run_test):
        self._run_test = run_test

    def run(self, result=None):
        return self._run_test.run(result)


def retry_flaky(run_test_factory=None):
    """
    Wrap a ``RunTest`` object so that flaky tests are retried.
    """
    if run_test_factory is None:
        run_test_factory = testtools.RunTest

    # XXX: I feel as if there's a simpler, more standard way of doing this.
    @wraps(run_test_factory)
    def wrapped(*args, **kwargs):
        return _RetryFlaky(run_test_factory(*args, **kwargs))
    return wrapped
