# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Logic for handling flaky tests.
"""

from functools import partial

from pyrsistent import PClass, field, pmap
import testtools
from testtools.testcase import gather_details


_FLAKY_ATTRIBUTE = '_flaky'


# TODO:
# - actually run a flaky test manually to see what everything looks like
# - make sure that JIRA data is included in flaky annotations
#   - do "either text or sequence" UI for jira_keys
# - attach details to success
# - handle tests with many different kinds of results


def flaky(jira_keys, max_runs=5, min_passes=2):
    """
    Mark a test as flaky.

    A 'flaky' test is one that sometimes passes but sometimes fails. Marking a
    test as flaky means both failures and successes are expected, and that
    neither will fail the test run.

    :param unicode jira_keys: The JIRA key of the bug for this flaky test,
        e.g. 'FLOC-2345'. Can also be a sequence of keys if the test is flaky
        fr multiple reasons.
    :param int max_runs: The maximum number of times to run the test.
    :param int min_passes: The minimum number of passes required to treat this
        test as successful.
    :return: A decorator that can be applied to `TestCase` methods.
    """
    # XXX: This raises a crappy error message if you forgot to provide a JIRA
    # key. Is there a way to provide a good one?

    # TODO (see FLOC-3281):
    # - allow specifying which exceptions are expected
    # - provide interesting & parseable logs for flaky tests

    annotation = _FlakyAnnotation(max_runs=max_runs, min_passes=min_passes)

    def wrapper(test_method):
        setattr(test_method, _FLAKY_ATTRIBUTE, annotation)
        return test_method

    return wrapper


def _get_flaky_attrs(case):
    """
    Get the flaky decoration detail from ``case``.

    :param TestCase case: A test case that might have been decorated with
        @flaky.
    :return: ``None`` if not flaky, or a ``pmap`` of the flaky test details.
    """
    # XXX: Is there a public way of doing this?
    method = case._get_test_method()
    return getattr(method, _FLAKY_ATTRIBUTE, None)


class _FlakyAnnotation(PClass):

    max_runs = field(int, mandatory=True,
                     invariant=lambda x: (x > 0, "must run at least once"))
    min_passes = field(int, mandatory=True,
                       invariant=lambda x: (x > 0, "must pass at least once"))

    __invariant__ = lambda x: (x.max_runs >= x.min_passes,
                               "Can't pass more than we run")


def retry_flaky(run_test_factory=None):
    """
    Wrap a ``RunTest`` object so that flaky tests are retried.
    """
    if run_test_factory is None:
        run_test_factory = testtools.RunTest

    return partial(_RetryFlaky, run_test_factory)


class _RetryFlaky(testtools.RunTest):
    """
    ``RunTest`` implementation that retries tests that fail.
    """
    # XXX: This should probably become a part of testtools:
    # https://bugs.launchpad.net/testtools/+bug/1515933

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
                self._case, result, flaky.min_passes, flaky.max_runs)

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

        while successes < min_passes and len(results) < max_runs:
            was_successful, details = self._attempt_test(case)
            if was_successful:
                successes += 1
            results.append(details)

        result.startTest(case)
        if successes >= min_passes:
            # XXX: Should attach a whole bunch of information here as details.
            result.addSuccess(case)
        else:
            # XXX: How are we going to report on tests that sometimes fail,
            # sometimes error. Probably "if all failures, failure; otherwise,
            # error"
            result.addError(case, details=_combine_details(results))
        result.stopTest(case)
        return result

    def _attempt_test(self, case):
        """
        Run 'case' with a temporary result.

        :param testtools.TestCase case: The test to run.

        :return: a tuple of ``(success, details)``, where ``success`` is
            a boolean indicating whether the test was successful or not
            and ``details`` is a dictionary of testtools details.
        """
        tmp_result = testtools.TestResult()
        self._run_test(case, tmp_result)
        details = pmap(case.getDetails())
        _reset_case(case)
        return tmp_result.wasSuccessful(), details


def _combine_details(detailses):
    """
    Take a sequence of details dictionaries and combine them into one.
    """
    # XXX: Only necessary becaause testtools's `gather_details` is perversely
    # mutatey.
    result = {}
    for details in detailses:
        gather_details(details, result)
    return pmap(result)


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
