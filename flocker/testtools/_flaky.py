# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Logic for handling flaky tests.
"""

from functools import partial

import flaky as _flaky
from pyrsistent import pmap
import testtools


def flaky(jira_key, max_runs=5, min_passes=2):
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


class _RetryFlaky(testtools.RunTest):
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

    def _run_prepared_result(self, result):
        """
        Run the test with a result that conforms to testtools' extended
        ``TestResult`` interface.

        This overrides a method in base ``RunTest`` which is intended to be
        overwritten.
        """
        flaky = _get_flaky_attrs(self._case)
        if flaky is not None:
            return self._run_flaky_test(
                self._case, result, flaky['min_passes'], flaky['max_runs'])

        # No flaky attributes? Then run as normal.
        return self._run_test(self._case, result)

    def _run_test(self, case, result):
        """
        Run ``case`` with the ``RunTest`` we are wrapping.

        :param testtools.TestCase case: The test to run.
        :param testtools.TestResult result: The test result to report to.
            Must conform to testtools extended test result interface.
        :return: The modified ``result``.
        """
        run_test = self._run_test_factory(case, *self._args, **self._kwargs)
        return run_test._run_prepared_result(result)

    def _run_flaky_test(self, case, result, min_passes, max_runs):
        """
        Run a test that has been decorated with the `@flaky` decorator.

        :param TestCase case: A ``testtools.TestCase`` to run.
        :param TestResult result: A ``TestResult`` object that conforms to the
            testtools extended result interface.
        :param int min_passes: The minimum number of successes required to
            consider the test successful.
        :param int max_runs: The maximum number of times to run the test.

        :return: A ``TestResult`` with the result of running the flaky test.
        """
        successes = 0
        results = []

        # XXX: I am too stupid to figure out whether these should be <=
        while successes < min_passes and len(results) < max_runs:
            tmp_result = testtools.TestResult()
            self._run_test(case, tmp_result)
            results.append(tmp_result)
            if tmp_result.wasSuccessful():
                successes += 1
            _reset_case(case)

        result.startTest(case)
        if successes >= min_passes:
            # XXX: Should attach a whole bunch of information here as details.
            result.addSuccess(case)
        else:
            # XXX: Need to actually provide data about the errors.
            # XXX: How are we going to report on tests that sometimes fail,
            # sometimes error. Probably "if all failures, failure; otherwise,
            # error"
            # XXX: Consider extracting this aggregation into a separate
            # function.
            result.addError(case, details={})
        result.stopTest(case)

        # XXX: Obviously we want to report failures!
        return result


def _reset_case(case):
    """
    Reset ``case`` so it can be run again.
    """
    # XXX: Alternative approach is to use clone_test_with_new_id, rather than
    # resetting the same test case.
    # Don't want details from last run.
    case.getDetails().clear()
    # https://github.com/testing-cabal/testtools/pull/165/ fixes this.
    case._TestCase__setup_called = False
    case._TestCase__teardown_called = False


def _get_flaky_attrs(case):
    """
    Get the flaky decoration detail from ``case``.

    :param TestCase case: A test case that might have been decorated with
        @flaky.
    :return: ``None`` if not flaky, or a ``pmap`` of the flaky test details.
    """
    # XXX: Is there a public way of doing this?
    method = case._get_test_method()
    max_runs = getattr(method, '_flaky_max_runs', None)
    min_passes = getattr(method, '_flaky_min_passes', None)
    if max_runs is None or min_passes is None:
        # XXX: This is a crappy way of deciding whether a method was decorated
        # or not, because it's ambiguous. Really, @flaky should set a single,
        # compound value on the method.
        return None
    # XXX: Should probably be a PClass.
    return pmap({
        'max_runs': max_runs,
        'min_passes': min_passes,
    })


def retry_flaky(run_test_factory=None):
    """
    Wrap a ``RunTest`` object so that flaky tests are retried.
    """
    if run_test_factory is None:
        run_test_factory = testtools.RunTest

    return partial(_RetryFlaky, run_test_factory)
