# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for ``flocker.common._interface``.
"""

from twisted.trial.unittest import SynchronousTestCase

from eliot.testing import (
    assertHasMessage, capture_logging
)
from eliot import Field, MessageType
from pyrsistent import PClass, field, InvariantException

from zope.interface import Interface, implementer

from .. import interface_decorator, provides


# Eliot structures for testing ``interface_decorator``.
METHOD = Field.for_types(
    u"method", [unicode],
    u"The name of the decorated method.")
TEST_MESSAGE = MessageType(u"flocker:common:test:interface:message",
                           [METHOD])
TEST_EXCEPTION = MessageType(u"flocker:common:test:interface:exception",
                             [METHOD])


class IDummy(Interface):
    """
    Dummy interface with two test methods.
    """
    def return_method():
        """
        Return something.
        """

    def raise_method():
        """
        Raise something.
        """


@implementer(IDummy)
class Dummy(object):
    """
    Dummy class that implements ``IDummy`` interface.

    Implements two methods: one to return an object, and the second
    to raise an ``Exception``.
    """
    def __init__(self, result):
        self._result = result

    def return_method(self):
        return self._result

    def raise_method(self):
        raise self._result


def _test_logged_method(method_name, original_name):
    """
    Decorator for logging message to Eliot logger.
    - Log before calling given ``method_name``.
    - Log if ``method_name`` resulted in an ``Exception``.
    """
    def _run_with_logging(self, *args, **kwargs):
        original = getattr(self, original_name)
        method = getattr(original, method_name)
        try:
            TEST_MESSAGE(method=method_name.decode("ascii")).write()
            return method(*args, **kwargs)
        except Exception:
            TEST_EXCEPTION(method=method_name.decode("ascii")).write()
            raise
    return _run_with_logging


def test_decorator(interface, original):
    """
    Consumer of ``interface_decorator``.
    """
    return interface_decorator(
        "test_decorator",
        interface,
        _test_logged_method,
        original,
    )


@test_decorator(IDummy, "_dummy")
class LoggingDummy(object):
    """
    Decorated class corresponding to ``Dummy`` object.
    """
    def __init__(self, dummy):
        self._dummy = dummy


class InterfaceDecoratorTests(SynchronousTestCase):
    """
    Tests for ``interface_decorator``.
    """
    @capture_logging(
        assertHasMessage,
        TEST_MESSAGE, {
            "method": u"return_method",
        },
    )
    def test_return(self, logger):
        """
        A decorated method returns the value returned by the original method,
        and logs expected text to Eliot.
        """
        result = object()
        logging_dummy = LoggingDummy(Dummy(result))
        self.assertIs(result, logging_dummy.return_method())

    @capture_logging(
        assertHasMessage,
        TEST_EXCEPTION, {
            "method": u"raise_method",
        },
    )
    def test_raise(self, logger):
        """
        A decorated method raises the same exception raised by the original
        method, and logs expected text to Eliot.
        """
        result = ValueError("Things.")
        logging_dummy = LoggingDummy(Dummy(result))
        exception = self.assertRaises(ValueError, logging_dummy.raise_method)
        self.assertIs(result, exception)


class InterfaceHolder(PClass):
    """
    ``PClass`` that has a field with a ``provides`` invariant.
    """
    value = field(invariant=provides(IDummy), mandatory=True)


class ProvidesTests(SynchronousTestCase):
    """
    Tests for ``provides``.
    """

    def test_interface_accepted(self):
        """
        When an object providing the given interface is provided,
        no invariant exception is raised.
        """
        InterfaceHolder(value=Dummy(object()))

    def test_other_rejected(self):
        """
        When an object not providing the given interface is provided,
        an ``InvariantException`` is raised.
        """
        self.assertRaises(
            InvariantException,
            InterfaceHolder, value=object(),
        )

    def test_invariant_message(self):
        """
        When an object not providing the given interface is provided,
        the message contains both the value and the interface it
        doesn't provide.
        """
        exception = self.assertRaises(
            InvariantException,
            InterfaceHolder, value=True,
        )
        self.assertEqual(
            exception.invariant_errors,
            ("True doesn't provide IDummy",),
        )

    def test_invariant_name(self):
        """
        The invariant functions name includes the interface being
        required.
        """
        invariant = provides(IDummy)
        self.assertEqual(
            invariant.__name__,
            'provides_IDummy_invariant',
        )
