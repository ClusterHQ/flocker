# Copyright ClusterHQ Inc.  See LICENSE file for details.
"""
Method tests for the control service benchmarks.
"""

from zope.interface import Interface

from flocker.testtools import TestCase

from benchmark._method import validate_no_arg_method, InvalidMethod


class ITest(Interface):
    """
    An interface for testing.
    """

    def noargs():
        """
        Method that takes no arguments.
        """

    def hasargs(a, b, c):
        """
        Method that takes arguments.
        """


class MethodTests(TestCase):

    def test_noargs_is_noargs_method(self):
        """
        A no-argument method validates as no-arg method.
        """
        validate_no_arg_method(ITest, 'noargs')

    def test_hasargs_fails_noargs_method(self):
        """
        An argument-taking method fails to validate as no-arg method.
        """
        exception = self.assertRaises(
            InvalidMethod, validate_no_arg_method, ITest, 'hasargs'
        )
        self.assertIn('requires parameters', str(exception))

    def test_not_present_fails_noargs_method(self):
        """
        A non-present method fails to validate as no-arg method.
        """
        exception = self.assertRaises(
            InvalidMethod, validate_no_arg_method, ITest, 'notpresent'
        )
        self.assertIn('not found in interface', str(exception))
