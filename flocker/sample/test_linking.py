# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Sample tests for skipping.
"""
from unittest import SkipTest, skipUnless
from twisted.trial.unittest import TestCase

skip_this_test = skipUnless(
    False, "This test should be skipped.")


class SkippedSetUp(TestCase):
    @skip_this_test
    def setUp(self):
        pass

    def test_not_decorated(self):
        pass

class SkippedTest(TestCase):
    def setUp(self):
        pass

    @skip_this_test
    def test_not_decorated(self):
        pass