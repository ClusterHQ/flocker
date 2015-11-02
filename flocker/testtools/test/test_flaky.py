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

    # XXX: Should I use this branch to introduce testtools as well?

    @given(integers())
    def test_decorated_function_executed(self, x):
        """
        ``@flaky`` decorates the given function sanely.
        """
        values = []

        @flaky
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

            @flaky
            def test_something(self):
                pass

        test = SomeTest('test_something')
        result = unittest.TestResult()

        test.run(result)

        self.assertEqual({}, result.__dict__)
