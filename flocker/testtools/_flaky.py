# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Logic for handling flaky tests.
"""

from functools import partial
from pprint import pformat

from eliot import Message
from pyrsistent import PClass, field, pmap, pset, pset_field
import testtools
from testtools.content import text_content
from testtools.testcase import gather_details
from twisted.python.constants import Names, NamedConstant


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


def _flaky_invariants(x):
    return (
        (x.max_runs >= x.min_passes, "Can't pass more than we run"),
        (len(x.jira_keys) > 0, "Must provide a jira key"),
    )


class _FlakyAnnotation(PClass):

    max_runs = field(int, mandatory=True,
                     invariant=lambda x: (x > 0, "must run at least once"))
    min_passes = field(int, mandatory=True,
                       invariant=lambda x: (x > 0, "must pass at least once"))
    jira_keys = pset_field(unicode, optional=False)

    __invariant__ = _flaky_invariants

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


def retry_flaky(run_test_factory=None):
    """
    Wrap a ``RunTest`` object so that flaky tests are retried.

    :param run_test_factory: A callable that takes a `TestCase` and returns
        something that behaves like `testtools.RunTest`.
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
        super(_RetryFlaky, self).__init__(case)
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
        result.startTest(case)
        successes = 0
        results = []

        # Optimization to stop running early if there's no way that we can
        # reach the minimum number of successes.
        max_fails = flaky.max_runs - flaky.min_passes
        while (successes < flaky.min_passes and
               len(results) - successes <= max_fails):
            was_successful, result_type, details = self._attempt_test(case)
            if was_successful:
                successes += 1
            results.append((result_type, details))
        successful = successes >= flaky.min_passes

        flaky_data = flaky.to_dict()
        flaky_data.update({'runs': len(results), 'passes': successes})
        flaky_details = {
            'flaky': text_content(pformat(flaky_data)),
        }
        combined_details = _combine_details(
            [flaky_details] + list(r[1] for r in results))

        if successful:
            skip_reported = False
            for result_type, details in results:
                if result_type == _ResultType.skip:
                    result.addSkip(case, details=details)
                    skip_reported = True

            if not skip_reported:
                Message.new(
                    message_type=u"flocker:test:flaky",
                    id=case.id(),
                    successes=successes,
                    passes=len(results),
                    min_passes=flaky.min_passes,
                    max_runs=flaky.max_runs,
                ).write()
                result.addSuccess(case, details=combined_details)
        else:
            # XXX: How are we going to report on tests that sometimes fail,
            # sometimes error, sometimes skip? Currently we just error.
            result.addError(case, details=combined_details)
        result.stopTest(case)
        return result

    def _attempt_test(self, case):
        """
        Run 'case' with a temporary result.

        :param testtools.TestCase case: The test to run.

        :return: a tuple of ``(successful, result, details)``, where
            ``successful`` is a boolean indicating whether the test was
            succcessful, ``result`` is a _ResultType indicating what the test
            result was and ``details`` is a dictionary of testtools details.
        """
        tmp_result = testtools.TestResult()
        # XXX: Still using internal API of testtools despite improvements in
        # #165. Will need to do follow-up work on testtools to ensure that
        # RunTest.run(case); RunTest.run(case) is supported.
        try:
            case._reset()
        except AttributeError:
            # We are using a fork of testtools, which unfortunately means that
            # we need to do special things to make sure we're using the latest
            # version. Raise an error message that will help people figure out
            # what they need to do.
            raise Exception(
                "Could not reset TestCase. Maybe upgrade your version of "
                "testtools: pip install --upgrade --process-dependency-links "
                ".[dev]")
        self._run_test(case, tmp_result)
        result_type = _get_result_type(tmp_result)
        details = pmap(case.getDetails())
        if result_type == _ResultType.skip:
            # XXX: Work around a testtools bug where it reports stack traces
            # for skips that aren't passed through its supported
            # SkipException: https://bugs.launchpad.net/testtools/+bug/1518100
            [reason] = list(tmp_result.skip_reasons.keys())
            details = details.discard('traceback').set(
                'reason', text_content(reason))
        return (tmp_result.wasSuccessful(), result_type, details)


class _ResultType(Names):
    """
    Different kinds of test results.
    """

    success = NamedConstant()
    error = NamedConstant()
    failure = NamedConstant()
    skip = NamedConstant()
    unexpected_success = NamedConstant()
    expected_failure = NamedConstant()


def _get_result_type(result):
    """
    Get the _ResultType for ``result``.

    :param testtools.TestResult result: A TestResult that has had exactly
        one test run on it.
    :raise ValueError: If ``result`` has run more than one test, or has more
        than one kind of result.
    :return: A _ResultType for that result.
    """
    if result.testsRun != 1:
        raise ValueError('%r has run %d tests, 1 expected' % (
            result, result.testsRun))

    total = sum(map(len, [
        result.errors, result.failures, result.unexpectedSuccesses,
        result.expectedFailures, result.skip_reasons]))
    if total > 1:
        raise ValueError(
            '%r has more than one kind of result: %r found' % (result, total))

    if len(result.errors) > 0:
        return _ResultType.error
    elif len(result.failures) > 0:
        return _ResultType.failure
    elif len(result.unexpectedSuccesses) > 0:
        return _ResultType.unexpected_success
    elif len(result.expectedFailures) > 0:
        return _ResultType.expected_failure
    elif len(result.skip_reasons) > 0:
        return _ResultType.skip
    else:
        return _ResultType.success


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
