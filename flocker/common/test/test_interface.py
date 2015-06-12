# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for ``flocker.common._interface``.
"""

from twisted.trial.unittest import SynchronousTestCase

from eliot.testing import (
    assertHasMessage, capture_logging
)
from eliot import Field, MessageType

from zope.interface import Interface, implementer

from .. import interface_decorator, interface_wrapper


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


from functools import wraps

class IFooBar(Interface):
    def foo():
        pass

    def bar():
        pass


@implementer(IFooBar)
class QuietFooBarAPI(object):
    def foo(self, number):
        return number

    def bar(self, number):
        return number


class InterfaceWrapperTests(SynchronousTestCase):
    """
    Tests for ``interface_wrapper``.
    """
    def test_object_instance_wrapper(self):
        """
        ``interface_wrapper`` returns a function which replaces all the
        methods defined in ``interface`` with wrappers and returns the
        modified object.
        """
        logger = []

        def _make_logging_method(original_method):
            @wraps(original_method)
            def logging_method(*args, **kwargs):
                logger.append((original_method, args, kwargs))
                return original_method(*args, **kwargs)
            return logging_method

        log_interface_methods = interface_wrapper(
            wrapper_name="log_interface_methods",
            method_wrapper_factory=_make_logging_method
        )

        quiet_api = QuietFooBarAPI()
        logging_api = log_interface_methods(
            IFooBar,
            quiet_api
        )
        return_values = [
            logging_api.foo(1),
            logging_api.bar(number=2)
        ]
        self.assertEqual([1, 2], return_values)
        self.assertEqual(
            [(logging_api.foo, (1,), {}),
             (logging_api.bar, (), {"number": 2})],
            logger
        )

    def test_non_provider_typeerror(self):
        """
        ``interface_decorator`` raises ``TypeError`` if supplied with a
        ``function`` as the decoratee.
        """
        def method_wrapper_factory(original_method):
            @wraps(original_method)
            def method_wrapper(*args, **kwargs):
                return original_method(*args, **kwargs)
            return method_wrapper

        pass_through_methods = interface_wrapper(
            wrapper_name="pass_through_methods",
            method_wrapper_factory=method_wrapper_factory
        )

        def some_undecorated_function():
            pass

        self.assertRaises(
            TypeError,
            pass_through_methods,
            interface=IDummy,
            original=some_undecorated_function
        )


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
