# Copyright ClusterHQ Ltd.  See LICENSE file for details.

"""
Tests for ``flocker.testtools._flaky``.
"""

from datetime import timedelta
from functools import partial
from itertools import repeat
from pprint import pformat
from StringIO import StringIO
import unittest

from hypothesis import given
from hypothesis.strategies import (
    integers,
    lists,
    permutations,
    streaming,
    text,
)
import testtools
from testtools.matchers import (
    AfterPreprocessing,
    Contains,
    Equals,
    HasLength,
    MatchesAll,
    MatchesStructure,
)

from .. import AsyncTestCase, async_runner
from .._flaky import (
    _FLAKY_ATTRIBUTE,
    _get_flaky_annotation,
    flaky,
    retry_flaky,
)


# A JIRA key is just some text.
jira_keys = text(average_size=5)

# Don't really want to run anything more than 5 times.
num_runs = integers(min_value=1, max_value=5)

# Used to run tests without emitting to stdout.
silent_async_runner = async_runner(
    timedelta(seconds=1), flaky_output=StringIO())


class FlakyTests(testtools.TestCase):
    """
    Tests for ``@flaky`` decorator.
    """

    @given(integers())
    def test_decorated_function_executed(self, x):
        """
        ``@flaky`` decorates the given function sanely.
        """
        values = []

        @flaky(u'FLOC-XXXX')
        def f(x):
            values.append(x)
            return x

        y = f(x)
        self.expectThat(y, Equals(x))
        self.assertThat(values, Equals([x]))

    def _get_annotation_dict(self, f):
        """
        Get the flaky annotation dictionary for flaky function ``f``.
        """
        return getattr(f, _FLAKY_ATTRIBUTE).to_dict()

    @given(jira_keys, num_runs, num_runs)
    def test_annotation_dictionary(self, jira_key, max_runs, min_passes):
        [min_passes, max_runs] = sorted([min_passes, max_runs])

        @flaky(jira_key, max_runs, min_passes)
        def f(x):
            pass

        self.assertThat(self._get_annotation_dict(f), Equals({
            'min_passes': min_passes,
            'max_runs': max_runs,
            'jira_keys': set([jira_key]),
        }))

    @given(lists(jira_keys, min_size=1, average_size=2), num_runs, num_runs)
    def test_annotation_dictionary_multiple_keys(self, jira_keys, max_runs,
                                                 min_passes):
        [min_passes, max_runs] = sorted([min_passes, max_runs])

        @flaky(jira_keys, max_runs, min_passes)
        def f(x):
            pass

        self.assertThat(self._get_annotation_dict(f), Equals({
            'min_passes': min_passes,
            'max_runs': max_runs,
            'jira_keys': set(jira_keys),
        }))

    @given(lists(jira_keys, min_size=1, average_size=2), num_runs, num_runs,
           lists(jira_keys, min_size=1, average_size=2), num_runs, num_runs)
    def test_multiple_decorators(self, jira_keys1, max_runs1, min_passes1,
                                 jira_keys2, max_runs2, min_passes2):
        [min_passes1, max_runs1] = sorted([min_passes1, max_runs1])
        [min_passes2, max_runs2] = sorted([min_passes2, max_runs2])

        @flaky(jira_keys1, max_runs1, min_passes1)
        @flaky(jira_keys2, max_runs2, min_passes2)
        def f(x):
            pass

        self.assertThat(self._get_annotation_dict(f), Equals({
            'min_passes': max(min_passes1, min_passes2),
            'max_runs': max(max_runs1, max_runs2),
            'jira_keys': set(jira_keys1) | set(jira_keys2),
        }))

    def test_successful_flaky_test(self):
        """
        A successful flaky test is considered successful.
        """

        # We use 'unittest' here to avoid accidentally depending on Twisted
        # TestCase features, thus increasing complexity.
        class SomeTest(AsyncTestCase):

            run_tests_with = silent_async_runner

            @flaky(u'FLOC-XXXX')
            def test_something(self):
                pass

        test = SomeTest('test_something')
        self.assertThat(run_test(test), has_results(tests_run=Equals(1)))

    @given(jira_keys, num_runs, num_runs)
    def test_always_erroring_flaky_test(self, jira_keys, max_runs, min_passes):
        """
        A flaky test always errors out is recorded as erroring.
        """
        [min_passes, max_runs] = sorted([min_passes, max_runs])

        executions = repeat(lambda: throw(ValueError('failure')))

        class SomeTest(AsyncTestCase):

            run_tests_with = silent_async_runner

            @flaky(jira_keys, max_runs=max_runs, min_passes=min_passes)
            def test_something(self):
                next(executions)()

        test = SomeTest('test_something')
        result = run_test(test)
        self.expectThat(
            result, has_results(
                errors=HasLength(1),
                tests_run=Equals(1),
            )
        )
        [(found_test, exception)] = result.errors
        flaky_data = _get_flaky_annotation(test).to_dict()
        flaky_data.update({'runs': max_runs - min_passes + 1, 'passes': 0})
        self.assertThat(
            exception, MatchesAll(
                Contains('ValueError'),
                Contains(pformat(flaky_data)),
            )
        )

    @given(permutations([
        lambda: throw(ValueError('failure')),
        lambda: None,
        lambda: throw(RuntimeError('failure #2')),
    ]))
    def test_intermittent_flaky_test(self, test_methods):
        """
        A @flaky test that fails sometimes and succeeds other times counts as a
        pass, as long as it passes more than the given min_passes threshold.
        """
        # XXX: We could create an "exceptions" strategy.
        executions = iter(test_methods)

        class SomeTest(AsyncTestCase):

            run_tests_with = silent_async_runner

            @flaky(u'FLOC-XXXX', max_runs=len(test_methods), min_passes=1)
            def test_something(self):
                next(executions)()

        test = SomeTest('test_something')
        self.assertThat(run_test(test), has_results(tests_run=Equals(1)))

    @given(permutations([
        lambda: throw(ValueError('failure')),
        lambda: None,
        lambda: throw(RuntimeError('failure #2')),
    ]))
    def test_intermittent_flaky_test_that_errors(self, test_methods):
        """
        Tests marked with 'flaky' are retried if they fail, and marked as
        erroring / failing if they don't reach the minimum number of successes.
        """
        executions = iter(test_methods)

        class SomeTest(testtools.TestCase):
            run_tests_with = retry_flaky(output=StringIO())

            @flaky(u'FLOC-XXXX', max_runs=len(test_methods), min_passes=2)
            def test_something(self):
                next(executions)()

        test = SomeTest('test_something')
        result = unittest.TestResult()
        test.run(result)
        self.assertThat(result, has_results(
            tests_run=Equals(1),
            errors=HasLength(1),
        ))

    @given(permutations([
        lambda: throw(ValueError('failure')),
        lambda: None,
        lambda: throw(RuntimeError('failure #2')),
    ]))
    def test_intermittent_flaky_subclass(self, test_methods):
        """
        We sometimes subclass test classes in order to test different
        implementations of the same interface. A test within such a subclass
        can be marked as flaky, causing it to retry.
        """
        executions = iter(test_methods)

        class SomeTest(testtools.TestCase):
            run_tests_with = retry_flaky(output=StringIO())

            def test_something(self):
                next(executions)()

        class SubclassTest(SomeTest):

            @flaky(u'FLOC-XXXX', max_runs=len(test_methods), min_passes=1)
            def test_something(self):
                super(SubclassTest, self).test_something()

        test = SubclassTest('test_something')
        result = unittest.TestResult()
        test.run(result)
        self.assertThat(result, has_results(tests_run=Equals(1)))

    @given(jira_keys, num_runs, num_runs,
           streaming(text(average_size=10)).map(iter))
    def test_flaky_skipped_test(self, jira_keys, max_runs, min_passes,
                                reasons):
        """
        If a test is skipped and also marked @flaky, we report it as skipped.
        """
        [min_passes, max_runs] = sorted([min_passes, max_runs])
        observed_reasons = []

        class SkippingTest(AsyncTestCase):
            run_tests_with = retry_flaky(output=StringIO())

            @flaky(jira_keys, max_runs, min_passes)
            def test_skip(self):
                observed_reasons.append(reasons.next())
                raise unittest.SkipTest(observed_reasons[-1])

        test = SkippingTest('test_skip')
        result = unittest.TestResult()
        test.run(result)
        self.assertThat(
            result,
            has_results(
                tests_run=Equals(1),
                skipped=AfterPreprocessing(
                    lambda xs: list(unicode(x[1]) for x in xs),
                    Equals(observed_reasons)),
            ))


def throw(exception):
    """
    Raise 'exception'.
    """
    raise exception


def has_results(errors=None, failures=None, skipped=None,
                expected_failures=None, unexpected_successes=None,
                tests_run=None):
    """
    Return a matcher on test results.

    By default, will match a result that has no tests run.
    """
    if errors is None:
        errors = Equals([])
    if failures is None:
        failures = Equals([])
    if skipped is None:
        skipped = Equals([])
    if expected_failures is None:
        expected_failures = Equals([])
    if unexpected_successes is None:
        unexpected_successes = Equals([])
    if tests_run is None:
        tests_run = Equals(0)
    return MatchesStructure(
        errors=errors,
        failures=failures,
        skipped=skipped,
        expectedFailures=expected_failures,
        unexpectedSuccesses=unexpected_successes,
        testsRun=tests_run,
    )


def run_test(case):
    """
    Run a test and return its results.
    """
    # XXX: How many times have I written something like this?
    result = unittest.TestResult()
    case.run(result)
    return result
