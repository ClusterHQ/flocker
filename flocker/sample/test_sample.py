# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Sample tests for skipping.
"""
from flocker.testtools.skips import skipUnless, skipIf, SkipTest
from twisted.trial.unittest import TestCase

skip_this_test_with_skipUnless = skipUnless(
    False, "This test should be skipped.")

skip_this_test_with_skipIf = skipIf(
    True, "This test should be skipped.")

class SkippedSetUp(TestCase):
    @skip_this_test_with_skipUnless
    def setUp(self):
        pass

    def test_not_decorated(self):
        pass

class SkippedTests(TestCase):
    @skip_this_test_with_skipUnless
    def test_decorated_with_skipUnless(self):
        pass

    @skip_this_test_with_skipIf
    def test_decorated_with_skipIf(self):
        pass

    def test_which_raises_skiptest(self):
        raise SkipTest(self, "Skipping this test.")
