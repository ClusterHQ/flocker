# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Helpers for tests for implementations of ``IStateChange``.
"""

__all__ = [
    "make_comparison_tests", "make_istatechange_tests",
]

from zope.interface.verify import verifyObject

from twisted.trial.unittest import SynchronousTestCase

from .. import IStateChange


def make_comparison_tests(klass, kwargs1, kwargs2):
    """
    Create tests to verify a class provides standard ``==`` and ``!=``
    behavior.

    :param klass: Class that implements ``IStateChange``.
    :param kwargs1: Keyword arguments to ``klass``.
    :param kwargs2: Keyword arguments to ``klass`` that create different change
        than ``kwargs1``.

    :return: ``SynchronousTestCase`` subclass named
             ``<klassname>ComparisonTests``.
    """
    class Tests(SynchronousTestCase):
        def test_equality(self):
            """
            Instances with the same arguments are equal.
            """
            self.assertTrue(klass(**kwargs1) == klass(**kwargs1))
            self.assertFalse(klass(**kwargs1) == klass(**kwargs2))

        def test_notequality(self):
            """
            Instance with different arguments are not equal.
            """
            self.assertTrue(klass(**kwargs1) != klass(**kwargs2))
            self.assertFalse(klass(**kwargs1) != klass(**kwargs1))
    Tests.__name__ = klass.__name__ + "ComparisonTests"
    return Tests


def make_istatechange_tests(klass, kwargs1, kwargs2):
    """
    Create tests to verify a class provides ``IStateChange``.

    :param klass: Class that implements ``IStateChange``.
    :param kwargs1: Keyword arguments to ``klass``.
    :param kwargs2: Keyword arguments to ``klass`` that create different
        change than ``kwargs1``.

    :return: ``SynchronousTestCase`` subclass named
        ``<klassname>IStateChangeTests``.
    """
    class Tests(make_comparison_tests(klass, kwargs1, kwargs2)):
        def test_interface(self):
            """
            The class implements ``IStateChange``.
            """
            self.assertTrue(verifyObject(IStateChange, klass(**kwargs1)))
    Tests.__name__ = klass.__name__ + "IStateChangeTests"
    return Tests
