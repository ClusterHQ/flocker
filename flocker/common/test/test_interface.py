# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for ``flocker.common.interface_decorator``.
"""

from twisted.trial.unittest import SynchronousTestCase

from eliot.testing import (
    LoggedMessage, assertContainsFields, capture_logging
)
from eliot import Field, MessageType

from zope.interface import Interface, implementer

from ..interface import interface_decorator


# Eliot structures for testing ``interface_decorator``.
METHOD = Field.for_types(
    u"method", [unicode],
    u"The name of the decorated method.")
TEST_MESSAGE = MessageType(u"flocker:common:test:interface:message", [METHOD],)
TEST_EXCEPTION = MessageType(u"flocker:common:test:interface:exception",
                             [METHOD],)


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
    Implements two methods: one to return an object,
    and the second to raise an ``Exception``.
    """
    def __init__(self, result):
        self._result = result

    def return_method(self):
        return self._result

    def raise_method(self):
        raise self._result


def _test_logged_method(method_name, original_name):
    """
    Decorator that logs a message to ``Eliot`` logger in two flows:
    1) Log before calling given ``method_name``.
    2) Log if ``method_name`` resulted in an ``Exception``.
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
    def test_return(self):
        """
        Decorated method returns the value returned by the original method.
        """
        result = object()
        logging_dummy = LoggingDummy(Dummy(result))
        self.assertIs(result, logging_dummy.return_method())

    @capture_logging(lambda self, logger: None)
    def test_decorated_method(self, logger):
        """
        Decorated method logs expected text to ``Eliot``.
        """
        result = object()
        logging_dummy = LoggingDummy(Dummy(result))
        logging_dummy.return_method()

        logged = LoggedMessage.of_type(
            logger.messages, TEST_MESSAGE,
        )[0]

        assertContainsFields(
            self, logged.message, {
                "method": u"return_method",
            },
        )

    def test_raise(self):
        """
        Decorated method raises the same exception raised by the original
        method.
        """
        result = ValueError("Things.")
        logging_dummy = LoggingDummy(Dummy(result))
        exception = self.assertRaises(ValueError, logging_dummy.raise_method)
        self.assertIs(result, exception)

    @capture_logging(lambda self, logger: None)
    def test_decorated_exception(self, logger):
        """
        Decorated method logs expected text to ``Eliot`` when ``Exception``
        is raised.
        """
        result = ValueError("Things.")
        logging_dummy = LoggingDummy(Dummy(result))
        self.assertRaises(ValueError, logging_dummy.raise_method)

        logged = LoggedMessage.of_type(
            logger.messages, TEST_EXCEPTION,
        )[0]

        assertContainsFields(
            self, logged.message, {
                "method": u"raise_method",
            },
        )
