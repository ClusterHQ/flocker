# Copyright ClusterHQ Ltd.  See LICENSE file for details.

"""
Tests for ``flocker.testtools._flaky``.
"""

from itertools import repeat
import unittest

from hypothesis import given
from hypothesis.strategies import integers
import testtools
from testtools.matchers import (
    Contains,
    Equals,
    HasLength,
    MatchesAll,
    MatchesStructure,
)

from .. import AsyncTestCase
from .._flaky import retry_flaky, flaky


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

        @flaky('FLOC-XXXX')
        def f(x):
            values.append(x)
            return x

        y = f(x)
        self.expectThat(y, Equals(x))
        self.assertThat(values, Equals([x]))

    def test_successful_flaky_test(self):
        """
        A successful flaky test is considered successful.
        """

        # We use 'unittest' here to avoid accidentally depending on Twisted
        # TestCase features, thus increasing complexity.
        class SomeTest(AsyncTestCase):

            @flaky('FLOC-XXXX')
            def test_something(self):
                pass

        test = SomeTest('test_something')
        self.assertThat(run_test(test), has_results(tests_run=Equals(1)))

    def test_always_failing_flaky_test(self):
        """
        As of FLOC-3414, the @flaky decorator doesn't actually treat failed
        tests in special in any way - it just acts as a structured comment.
        """

        executions = repeat(lambda: throw(ValueError('failure')))

        class SomeTest(AsyncTestCase):

            @flaky('FLOC-XXXX')
            def test_something(self):
                next(executions)()

        test = SomeTest('test_something')
        self.assertThat(
            run_test(test), has_results(
                errors=HasLength(1),
                tests_run=Equals(1),
            )
        )

    def test_intermittent_flaky_test(self):
        """
        A @flaky test that fails sometimes and succeeds other times counts as a
        pass, as long as it passes more than the given min_passes threshold.
        """
        # XXX: Do we have a 'shuffled' strategy?
        # XXX: We could create an "exceptions" strategy.
        executions = iter([
            lambda: throw(ValueError('failure')),
            lambda: None,
            lambda: throw(RuntimeError('failure #2')),
        ])

        class SomeTest(AsyncTestCase):

            @flaky('FLOC-XXXX', max_runs=3, min_passes=1)
            def test_something(self):
                next(executions)()

        test = SomeTest('test_something')
        self.assertThat(run_test(test), has_results(tests_run=Equals(1)))

    def test_intermittent_flaky_test_that_errors(self):
        """
        Tests marked with 'flaky' are retried if they fail, and marked as
        erroring / failing if they don't reach the minimum number of successes.
        """

        executions = iter([
            lambda: throw(ValueError('failure')),
            lambda: None,
            lambda: throw(RuntimeError('failure #2')),
        ])

        class SomeTest(testtools.TestCase):
            run_tests_with = retry_flaky()

            @flaky('FLOC-XXXX', max_runs=3, min_passes=2)
            def test_something(self):
                next(executions)()

        test = SomeTest('test_something')
        result = unittest.TestResult()
        test.run(result)
        self.expectThat(result, has_results(
            tests_run=Equals(1),
            errors=HasLength(1),
        ))
        [(found_test, exception)] = result.errors
        self.assertThat(
            exception, MatchesAll(
                Contains('ValueError'),
                Contains('RuntimeError'),
            )
        )


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
