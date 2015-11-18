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
        self.assertEqual({
            'errors': 0,
            'failures': 0,
            'skipped': 0,
            'expectedFailures': 0,
            'unexpectedSuccesses': 0,
            'testsRun': 1,
        }, get_results(test))

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
        self.assertEqual({
            'errors': 1,
            'failures': 0,
            'skipped': 0,
            'expectedFailures': 0,
            'unexpectedSuccesses': 0,
            'testsRun': 1,
        }, get_results(test))


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
