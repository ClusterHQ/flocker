"""
Tests for flocker base test cases.
"""

from hypothesis import given
from hypothesis.strategies import binary
from testtools import TestCase
from testtools.testresult.doubles import Python27TestResult
from twisted.trial import unittest

from .._base import AsyncTestCase


class AsyncTestCaseTests(TestCase):

    @given(binary())
    def test_trial_skip_exception(self, reason):
        """
        If tests raise the ``SkipTest`` exported by Trial, then that's
        recorded as a skip.
        """

        class SkippingTest(AsyncTestCase):
            def test_skip(self):
                raise unittest.SkipTest(reason)

        test = SkippingTest('test_skip')
        result = Python27TestResult()
        test.run(result)
        self.assertEqual([
            ('startTest', test),
            ('addSkip', test, reason),
            ('stopTest', test),
        ], result._events)
