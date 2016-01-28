# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for ``flocker.common._interface``.
"""

from eliot.testing import (
    assertHasMessage, capture_logging
)
from eliot import Field, MessageType
from pyrsistent import PClass, field, InvariantException

from testtools.matchers import Is, Equals, Raises, MatchesException

from zope.interface import Interface, implementer

from .. import (
    interface_decorator, provides, validate_signature_against_kwargs,
    InvalidSignature,
)
from ...testtools import TestCase


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


class InterfaceDecoratorTests(TestCase):
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


class ProvidesTests(TestCase):
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


def _raises_invalid_signature(**kwargs):
    """
    Helper function to create a matcher that matches callables that, when
    executed, raise an ``InvalidSignature`` that is equal to an
    ``InvalidSignature`` created with the passed in keyword arguments.

    :param **kwargs: keyword arguments to pass into an ``InvalidSignature``
        constructor.

    :returns: A matcher to use in tests.
    """
    return Raises(MatchesException(
        InvalidSignature,
        Equals(InvalidSignature(**kwargs))
    ))


def _no_arguments_function():
    pass


def _one_argument_function(arg):
    pass


def _one_default_argument_function(arg=None):
    pass


def _mixed_arguments_function(one, two=None, three=None, four=None):
    pass


def _args_fun(one, *args):
    pass


def _kwargs_fun(one, **kwargs):
    pass


def _args_kwargs_fun(one, *args, **kwargs):
    pass


class ValidateSignatureAgainstKwargsTests(TestCase):
    """
    Tests for :func:`validate_signature_against_kwargs`.
    """

    def test_no_arguments_validation_success(self):
        """
        :func:`validate_signature_against_kwargs` returns ``None`` if the
        function has no arguments, and an empty set is passed in.
        """
        self.assertThat(
            validate_signature_against_kwargs(_no_arguments_function, set()),
            Is(None)
        )

    def test_no_arguments_validation_failure(self):
        """
        :func:`validate_signature_against_kwargs` raises an
        ``InvalidSignature`` exception if the function has no arguments but an
        argument is passed in.
        """
        self.expectThat(
            lambda: validate_signature_against_kwargs(_no_arguments_function,
                                                      set(["arg"])),
            _raises_invalid_signature(unexpected_arguments=set(["arg"]))
        )

    def test_one_argument_validation_failure_differs(self):
        """
        :func:`validate_signature_against_kwargs` raises an
        ``InvalidSignature`` exception if the function takes one argument, but
        is passed an argument with a different name.
        """
        self.assertThat(
            lambda: validate_signature_against_kwargs(_one_argument_function,
                                                      set(["bad"])),
            _raises_invalid_signature(missing_arguments=set(["arg"]),
                                      unexpected_arguments=set(["bad"]))
        )

    def test_one_argument_validation_failure_too_many(self):
        """
        :func:`validate_signature_against_kwargs` raises an
        ``InvalidSignature`` exception if the function takes one argument, but
        is passed two arguments.
        """
        self.assertThat(
            lambda: validate_signature_against_kwargs(_one_argument_function,
                                                      set(["arg", "two"])),
            _raises_invalid_signature(unexpected_arguments=set(["two"]))
        )

    def test_one_argument_validation_success(self):
        """
        :func:`validate_signature_against_kwargs` returns ``None`` if it
        receives one expected argument.
        """
        self.assertThat(
            validate_signature_against_kwargs(_one_argument_function,
                                              set(["arg"])),
            Is(None)
        )

    def test_default_with_no_args_success(self):
        """
        :func:`validate_signature_against_kwargs` returns ``None`` if it
        receives zero arguments and all arguments have defaults.
        """
        self.assertThat(
            validate_signature_against_kwargs(_one_default_argument_function,
                                              set()),
            Is(None)
        )

    def test_default_wrong_arg_failure(self):
        """
        :func:`validate_signature_against_kwargs` raises an
        ``InvalidSignature`` exception if a function has one argument with a
        default, and a single wrong argument is passed in.
        """
        self.assertThat(
            lambda: validate_signature_against_kwargs(
                _one_default_argument_function, set(["unexpected"])),
            _raises_invalid_signature(unexpected_arguments=set(["unexpected"]),
                                      missing_optional_arguments=set(["arg"]))
        )

    def test_mixed_missing_mandatory_failure(self):
        """
        :func:`validate_signature_against_kwargs` raises an
        ``InvalidSignature`` exception if a function that has one mandatory
        argument is not specified, and the missing optional arguments are
        included in the exception.
        """
        self.assertThat(
            lambda: validate_signature_against_kwargs(
                _mixed_arguments_function, set(["two", "four"])),
            _raises_invalid_signature(
                missing_arguments=set(["one"]),
                missing_optional_arguments=set(["three"]))
        )

    def test_args_fun_success(self):
        """
        :func:`validate_signature_against_kwargs` returns None if no arguments
        are specified beyond the named arguments even if the function has an
        *args argument.
        """
        self.assertThat(
            validate_signature_against_kwargs(
                _args_fun, set(["one"])), Is(None)
        )

    def test_args_fun_failure(self):
        """
        :func:`validate_signature_against_kwargs` raises an
        ``InvalidSignature`` exception if a function that has *args but no
        **kwargs is called with keyword arguments beyond the specified
        arguments.
        """
        self.assertThat(
            lambda: validate_signature_against_kwargs(
                _args_fun, set(["one", "unexpected"])),
            _raises_invalid_signature(
                unexpected_arguments=set(["unexpected"]))
        )

    def test_kwargs_fun_failure(self):
        """
        :func:`validate_signature_against_kwargs` raises an
        ``InvalidSignature`` exception if a function that has **kwargs is
        missing one of the mandatory arguments.
        """
        self.assertThat(
            lambda: validate_signature_against_kwargs(
                _kwargs_fun, set(["cat"])),
            _raises_invalid_signature(
                missing_arguments=set(["one"]))
        )

    def test_kwargs_fun_success(self):
        """
        :func:`validate_signature_against_kwargs` returns None if arguments
        are specified beyond the named arguments if the function has an
        **kwargs argument.
        """
        self.assertThat(
            validate_signature_against_kwargs(
                _kwargs_fun, set(["one", "cat", "dog"])), Is(None)
        )

    def test_args_kwargs_fun_failure(self):
        """
        :func:`validate_signature_against_kwargs` raises an
        ``InvalidSignature`` exception if a function that has **kwargs and
        *args is missing one of the mandatory arguments.
        """
        self.assertThat(
            lambda: validate_signature_against_kwargs(
                _kwargs_fun, set(["cat"])),
            _raises_invalid_signature(
                missing_arguments=set(["one"]))
        )

    def test_args_kwargs_fun_success(self):
        """
        :func:`validate_signature_against_kwargs` returns None if arguments
        are specified beyond the named arguments if the function has *args and
        **kwargs arguments.
        """
        self.assertThat(
            validate_signature_against_kwargs(
                _kwargs_fun, set(["one", "cat", "dog"])), Is(None)
        )
