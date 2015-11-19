# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Logic for handling flaky tests.
"""

from functools import partial
from pprint import pformat
import sys

from pyrsistent import PClass, field, pmap, pset, pset_field
import testtools
from testtools.content import text_content
from testtools.testcase import gather_details


_FLAKY_ATTRIBUTE = '_flaky'


def flaky(jira_keys, max_runs=3, min_passes=1):
    """
    Mark a test as flaky.

    A 'flaky' test is one that sometimes passes but sometimes fails. Marking a
    test as flaky means both failures and successes are expected, and that
    neither will fail the test run.

    If a test has already been marked as flaky, applying ``@flaky`` a second
    time will add JIRA key information, and set the ``max_runs`` and
    ``min_passes`` to the larger of the provided values.

    :param unicode jira_keys: The JIRA key of the bug for this flaky test,
        e.g. 'FLOC-2345'. Can also be a sequence of keys if the test is flaky
        for multiple reasons.
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

    if isinstance(jira_keys, unicode):
        jira_keys = [jira_keys]

    annotation = _FlakyAnnotation(
        jira_keys=pset(jira_keys), max_runs=max_runs, min_passes=min_passes)

    def wrapper(test_method):
        existing_flaky = getattr(test_method, _FLAKY_ATTRIBUTE, None)
        if existing_flaky is None:
            note = annotation
        else:
            note = _combine_flaky_annotation(annotation, existing_flaky)
        setattr(test_method, _FLAKY_ATTRIBUTE, note)
        return test_method

    return wrapper


def _get_flaky_annotation(case):
    """
    Get the flaky decoration detail from ``case``.

    :param TestCase case: A test case that might have been decorated with
        @flaky.
    :return: ``None`` if not flaky, or a ``pmap`` of the flaky test details.
    """
    # XXX: Alas, there's no public way of doing this:
    # https://bugs.launchpad.net/testtools/+bug/1517867
    method = case._get_test_method()
    return getattr(method, _FLAKY_ATTRIBUTE, None)


class _FlakyAnnotation(PClass):

    max_runs = field(int, mandatory=True,
                     invariant=lambda x: (x > 0, "must run at least once"))
    min_passes = field(int, mandatory=True,
                       invariant=lambda x: (x > 0, "must pass at least once"))
    jira_keys = pset_field(unicode, optional=False)

    __invariant__ = lambda x: (
        (x.max_runs >= x.min_passes, "Can't pass more than we run"),
        (len(x.jira_keys) > 0, "Must provide a jira key"),
    )

    def to_dict(self):
        return {
            'max_runs': self.max_runs,
            'min_passes': self.min_passes,
            'jira_keys': set(self.jira_keys),
        }


def _combine_flaky_annotation(flaky1, flaky2):
    """
    Combine two flaky annotations.
    """
    return _FlakyAnnotation(
        jira_keys=flaky1.jira_keys | flaky2.jira_keys,
        max_runs=max(flaky1.max_runs, flaky2.max_runs),
        min_passes=max(flaky1.min_passes, flaky2.min_passes),
    )


def retry_flaky(run_test_factory=None, output=None):
    """
    Wrap a ``RunTest`` object so that flaky tests are retried.

    :param run_test_factory: A callable that takes a `TestCase` and returns
        something that behaves like `testtools.RunTest`.
    :param file output: A file-like object to which we'll send output about
        flaky tests. This is a temporary measure until we fix FLOC-3469, at
        which point we will just use standard logging.
    """
    if run_test_factory is None:
        run_test_factory = testtools.RunTest
    if output is None:
        output = sys.stdout

    return partial(_RetryFlaky, output, run_test_factory)


class _RetryFlaky(testtools.RunTest):
    """
    ``RunTest`` implementation that retries tests that fail.
    """
    # XXX: This should probably become a part of testtools:
    # https://bugs.launchpad.net/testtools/+bug/1515933

    def __init__(self, output, run_test_factory, case, *args, **kwargs):
        self._output = output
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
        flaky = _get_flaky_annotation(self._case)
        if flaky is not None:
            return self._run_flaky_test(self._case, result, flaky)

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

    def _run_flaky_test(self, case, result, flaky):
        """
        Run a test that has been decorated with the `@flaky` decorator.

        :param TestCase case: A ``testtools.TestCase`` to run.
        :param TestResult result: A ``TestResult`` object that conforms to the
            testtools extended result interface.
        :param _FlakyAnnotation flaky: A description of the conditions of
            flakiness.

        :return: A ``TestResult`` with the result of running the flaky test.
        """
        successes = 0
        results = []

        # Optimization to stop running early if there's no way that we can
        # reach the minimum number of successes.
        max_fails = flaky.max_runs - flaky.min_passes
        while (successes < flaky.min_passes and
               len(results) - successes <= max_fails):
            was_successful, details = self._attempt_test(case)
            if was_successful:
                successes += 1
            results.append(details)

        flaky_data = flaky.to_dict()
        flaky_data.update({'runs': len(results), 'passes': successes})
        flaky_details = {
            'flaky': text_content(pformat(flaky_data)),
        }

        details = _combine_details([flaky_details] + results)
        result.startTest(case)
        if successes >= flaky.min_passes:
            self._output.write(
                '@flaky(%s): passed %d out of %d runs '
                '(min passes: %d; max runs: %d)'
                % (case.id(), successes, len(results), flaky.min_passes,
                   flaky.max_runs)
            )

            result.addSuccess(case, details=details)
        else:
            # XXX: How are we going to report on tests that sometimes fail,
            # sometimes error, sometimes skip? Currently we just error.
            result.addError(case, details=details)
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
