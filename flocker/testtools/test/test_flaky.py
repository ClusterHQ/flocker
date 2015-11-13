# Copyright ClusterHQ Ltd.  See LICENSE file for details.

"""
Tests for ``flocker.testtools._flaky``.
"""

from itertools import repeat
import unittest

from hypothesis import given
from hypothesis.strategies import integers
import testtools

from .. import AsyncTestCase, TestCase
from .._flaky import retry_flaky, flaky


class FlakyTests(TestCase):
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
        self.assertEqual(y, x)
        self.assertEqual([x], values)

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
        self.assertEqual({
            'errors': 0,
            'failures': 0,
            'skipped': 0,
            'expectedFailures': 0,
            'unexpectedSuccesses': 0,
            'testsRun': 1,
        }, get_results(test))

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
        self.assertEqual({
            'errors': 1,
            'failures': 0,
            'skipped': 0,
            'expectedFailures': 0,
            'unexpectedSuccesses': 0,
            'testsRun': 1,
        }, get_results(test))

    def test_intermittent_flaky_test(self):
        """
        A @flaky test that fails sometimes and succeeds other times counts as a
        pass.
        """
        # XXX: Pass through again and update descriptions and tests for
        # min_value & max_value.
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
        self.assertEqual({
            'errors': 0,
            'failures': 0,
            'skipped': 0,
            'expectedFailures': 0,
            'unexpectedSuccesses': 0,
            'testsRun': 1,
        }, get_results(test))
    test_intermittent_flaky_test.todo = "Acceptance test for flaky retries"


class RetryFlakyTests(TestCase):
    """
    Tests for our ``RunTest`` implementation that retries flaky tests.
    """

    def test_executes_test(self):
        """
        Tests that the ``retry_flaky`` test runner are still run as normal.
        """

        values = []

        class NormalTest(testtools.TestCase):
            run_tests_with = retry_flaky()

            def test_something(self):
                values.append('foo')

        results = get_results(NormalTest('test_something'))
        self.assertEqual(['foo'], values)
        self.assertEqual({
            'errors': 0,
            'failures': 0,
            'skipped': 0,
            'expectedFailures': 0,
            'unexpectedSuccesses': 0,
            'testsRun': 1,
        }, results)


def throw(exception):
    """
    Raise 'exception'.
    """
    raise exception


def _get_result_stats(result):
    """
    Return a summary of test results.
    """
    return {
        'errors': len(result.errors),
        'failures': len(result.failures),
        'skipped': len(result.skipped),
        'expectedFailures': len(result.expectedFailures),
        'unexpectedSuccesses': len(result.unexpectedSuccesses),
        'testsRun': result.testsRun,
    }


def get_results(test):
    """
    Run a test and return a summary of its results.
    """
    result = unittest.TestResult()
    test.run(result)
    return _get_result_stats(result)
