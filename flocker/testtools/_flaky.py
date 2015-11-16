# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Logic for handling flaky tests.
"""

from functools import partial

import flaky as _flaky
import testtools


def flaky(jira_key, max_runs=None, min_passes=None):
    """
    Mark a test as flaky.

    A 'flaky' test is one that sometimes passes but sometimes fails. Marking a
    test as flaky means both failures and successes are expected, and that
    neither will fail the test run.

    :param unicode jira_key: The JIRA key of the bug for this flaky test,
        e.g. 'FLOC-2345'
    :param int max_runs: The maximum number of times to run the test.
    :param int min_passes: The minimum number of passes required to treat this
        test as successful.
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
        return _flaky.flaky(max_runs=max_runs, min_passes=min_passes)(
            test_method)
    return wrapper


class _RetryFlaky(object):
    """
    ``RunTest`` implementation that retries tests that fail.
    """
    # XXX: Make this a pyrsistent object

    # XXX: This should probably become a part of testtools:
    # https://bugs.launchpad.net/testtools/+bug/1515933

    # TODO: I think the "right" thing to do is to take a RunTest factory and
    # construct RunTest once per test run, each time giving it a newly-created
    # TestResult.
    #
    # When we're "done", we aggregate all of the results and output that to
    # the result we were given.

    def __init__(self, run_test_factory, case, *args, **kwargs):
        self._run_test_factory = run_test_factory
        self._case = case
        self._args = args
        self._kwargs = kwargs

    def run(self, result=None):
        return self._run_test_factory(
            self._case, *self._args, **self._kwargs).run(result)


def retry_flaky(run_test_factory=None):
    """
    Wrap a ``RunTest`` object so that flaky tests are retried.
    """
    if run_test_factory is None:
        run_test_factory = testtools.RunTest

    return partial(_RetryFlaky, run_test_factory)
