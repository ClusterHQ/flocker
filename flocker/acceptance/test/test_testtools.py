# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for flocker.acceptance.testtools.
"""

from eliot import ActionType
from eliot.testing import (
    assertContainsFields,
    assertHasAction,
    capture_logging,
)
from twisted.internet.defer import succeed

from ..testtools import (log_method, _ensure_encodeable)
from ...testtools import TestCase


class EnsureEncodeableTests(TestCase):
    """
    Tests for ``_ensure_encodeable``.

    ``_ensure_encodeable`` is an implementation detail of ``log_method``, so
    these tests are not strictly necessary. They were written because we were
    seeing unexpected behavior and wanted to make sure that
    ``_ensure_encodeable`` wasn't the cause.
    """

    def test_encodeable(self):
        """
        If given a JSON-encodeable object, _ensure_encodeable just returns it.
        """
        value = {'foo': 'bar'}
        self.assertEqual(value, _ensure_encodeable(value))

    def test_unencodeable(self):
        """
        If given an object that cannot be JSON encoded, _ensure_encodeable
        returns its repr.
        """
        value = object()
        self.assertEqual(repr(value), _ensure_encodeable(value))

    def test_circular(self):
        """
        If given an object with a circular reference, _ensure_encodeable
        returns its repr.
        """
        value = []
        value.append(value)
        self.assertEqual(repr(value), _ensure_encodeable(value))


class LogMethodTests(TestCase):
    """
    Tests for ``log_method``.
    """

    def make_action_type(self, action_type):
        """
        Eliot makes it tricky to create ``ActionType`` objects. Here's a
        helper to declutter our tests.
        """
        return ActionType(action_type, [], [])

    def _logs_action_test(self, logger, arg, kwarg, result):
        """
        Call a method ``f`` wrapped in ``log_method`` passing it ``arg`` as an
        argument, ``kwarg`` as a keyword argument and returning ``result`` as
        its result.

        :return: The logged action.
        """
        class Foo(object):
            @log_method
            def f(self, foo, bar):
                return succeed(result)

        foo = Foo()
        d = foo.f(arg, bar=kwarg)
        self.assertEqual(result, self.successResultOf(d))

        action_type = self.make_action_type('acceptance:f')
        return assertHasAction(
            self, logger, action_type, True,
        )

    def assert_call_parameters_logged(self, action, arg, kwarg, result):
        """
        Assert 'action' has start message that includes the argument and
        keyword argument given, and an end message that includes the result.
        """
        assertContainsFields(
            self, action.start_message,
            {'args': (arg,), 'kwargs': {'bar': kwarg}})
        assertContainsFields(
            self, action.end_message,
            {'result': result})

    @capture_logging(None)
    def test_logs_action_unserializable(self, logger):
        """
        Methods decorated with ``log_method`` have their start and end points
        logged as actions.

        When the args, kwargs, or return value are unserializable, we log the
        repr of same.
        """
        result = object()
        arg = object()
        kwarg = object()

        action = self._logs_action_test(logger, arg, kwarg, result)
        self.assert_call_parameters_logged(
            action, repr(arg), repr(kwarg), repr(result))

    @capture_logging(None)
    def test_logs_action_serializable(self, logger):
        """
        Methods decorated with ``log_method`` have their start and end points
        logged as actions.

        When the args, kwargs, or return value are serializable, we let eliot
        take care of serializing them. "Serializable" means json.dumps doesn't
        explode.
        """
        result = 42
        arg = b"hello"
        kwarg = {u'foo': 37}

        action = self._logs_action_test(logger, arg, kwarg, result)
        self.assert_call_parameters_logged(action, arg, kwarg, result)
