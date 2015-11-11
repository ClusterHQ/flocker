"""
Tests for flocker base test cases.
"""

import errno
import shutil

from hypothesis import given
from hypothesis.strategies import binary
from testtools import TestCase
from testtools.matchers import DirExists, Not, PathExists
from testtools.testresult.doubles import Python27TestResult
from twisted.python.filepath import FilePath
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

    def test_mktemp_doesnt_exist(self):
        """
        ``mktemp`` returns a path that doesn't exist inside a directory that
        does.
        """

        class SomeTest(AsyncTestCase):
            def test_pass(self):
                pass

        test = SomeTest('test_pass')
        temp_path = FilePath(test.mktemp())
        self.addCleanup(_remove_dir, temp_path.parent())

        self.expectThat(temp_path.parent().path, DirExists())
        self.assertThat(temp_path.path, Not(PathExists()))


def _remove_dir(path):
    """
    Safely remove the directory 'path'.
    """
    try:
        shutil.rmtree(path.path)
    except OSError as e:
        if e.errno != errno.ENOENT:
            raise
