# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Helpers for tests for implementations of ``IStateChange``.
"""

from zope.interface.verify import verifyObject

from zope.interface import implementer

from eliot import Logger, start_action

from pyrsistent import PClass, field
from characteristic import attributes

from twisted.internet.defer import succeed

from ...testtools import TestCase
from .. import IStateChange


__all__ = [
    "make_comparison_tests", "make_istatechange_tests",
]


def make_comparison_tests(klass, kwargs1, kwargs2):
    """
    Create tests to verify a class provides standard ``==`` and ``!=``
    behavior.

    :param klass: Class that implements ``IStateChange``.
    :param kwargs1: Keyword arguments to ``klass``.  Either a ``dict`` or a
        no-argument callable which returns keyword arguments to use.
    :param kwargs2: Keyword arguments to ``klass`` that create different change
        than ``kwargs1``.  Either a ``dict`` or a no-argument callable which
        returns keyword arguments to use.

    :return: ``SynchronousTestCase`` subclass named
             ``<klassname>ComparisonTests``.
    """
    def instance(kwargs):
        if isinstance(kwargs, dict):
            return klass(**kwargs)
        return klass(**kwargs())

    class Tests(TestCase):
        def test_equality(self):
            """
            Instances with the same arguments are equal.
            """
            self.assertTrue(instance(kwargs1) == instance(kwargs1))
            self.assertFalse(instance(kwargs1) == instance(kwargs2))

        def test_notequality(self):
            """
            Instance with different arguments are not equal.
            """
            self.assertTrue(instance(kwargs1) != instance(kwargs2))
            self.assertFalse(instance(kwargs1) != instance(kwargs1))
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
    def instance(kwargs):
        if isinstance(kwargs, dict):
            return klass(**kwargs)
        return klass(**kwargs())

    class Tests(make_comparison_tests(klass, kwargs1, kwargs2)):
        def test_interface(self):
            """
            The class implements ``IStateChange``.
            """
            self.assertTrue(verifyObject(IStateChange, instance(kwargs1)))
    Tests.__name__ = klass.__name__ + "IStateChangeTests"
    return Tests


@implementer(IStateChange)
class DummyStateChange(PClass):
    """
    A do-nothing implementation of ``IStateChange``.
    """
    value = field()

    @property
    def eliot_action(self):
        return start_action(Logger(), u"flocker:tests:dummy_state_change")

    def run(self, deployer):
        return succeed(None)


@implementer(IStateChange)
@attributes(["value"])
class RunSpyStateChange(object):
    """
    An implementation of ``IStateChange`` that records its runs.
    """
    @property
    def eliot_action(self):
        return start_action(Logger(), u"flocker:tests:run_spy_state_change")

    def run(self, deployer):
        self.value += 1
        return succeed(None)
