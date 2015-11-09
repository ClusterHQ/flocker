# Copyright ClusterHQ Ltd.  See LICENSE file for details.

"""
Tests for ``flocker.testtools._flaky``.
"""

import unittest

from hypothesis import given
from hypothesis.strategies import integers

from twisted.trial.unittest import SynchronousTestCase

from .._flaky import flaky


class FlakyTests(SynchronousTestCase):
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
        class SomeTest(unittest.TestCase):

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

    def test_failed_flaky_test(self):
        """
        As of FLOC-3414, the @flaky decorator doesn't actually treat failed
        tests in special in any way - it just acts as a structured comment.
        """

        class SomeTest(unittest.TestCase):

            @flaky('FLOC-XXXX')
            def test_something(self):
                1/0

        test = SomeTest('test_something')
        self.assertEqual({
            'errors': 1,
            'failures': 0,
            'skipped': 0,
            'expectedFailures': 0,
            'unexpectedSuccesses': 0,
            'testsRun': 1,
        }, get_results(test))


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
