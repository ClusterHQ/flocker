# Copyright ClusterHQ Ltd.  See LICENSE file for details.

"""
Tests for ``flocker.common._retry``.
"""

from itertools import repeat

from eliot.testing import (
    capture_logging,
    LoggedAction, LoggedMessage,
    assertContainsFields,
)

from twisted.internet.defer import succeed
from twisted.trial.unittest import SynchronousTestCase
from twisted.internet.task import Clock
from twisted.python.failure import Failure

from .._retry import (
    LOOP_UNTIL_ACTION,
    LOOP_UNTIL_ITERATION_MESSAGE,
    LoopExceeded,
    loop_until,
    retry_failure,
    poll_until,
)


class LoopUntilTests(SynchronousTestCase):
    """
    Tests for :py:func:`loop_until`.
    """

    @capture_logging(None)
    def test_immediate_success(self, logger):
        """
        If the predicate returns something truthy immediately, then
        ``loop_until`` returns a deferred that has already fired with that
        value.
        """
        result = object()

        def predicate():
            return result
        clock = Clock()
        d = loop_until(clock, predicate)
        self.assertEqual(
            self.successResultOf(d),
            result)

        action = LoggedAction.of_type(logger.messages, LOOP_UNTIL_ACTION)[0]
        assertContainsFields(self, action.start_message, {
            'predicate': predicate,
        })
        assertContainsFields(self, action.end_message, {
            'action_status': 'succeeded',
            'result': result,
        })

    @capture_logging(None)
    def test_iterates(self, logger):
        """
        If the predicate returns something falsey followed by something truthy,
        then ``loop_until`` returns it immediately.
        """
        result = object()
        results = [None, result]

        def predicate():
            return results.pop(0)
        clock = Clock()

        d = loop_until(clock, predicate)

        self.assertNoResult(d)

        clock.advance(0.1)
        self.assertEqual(
            self.successResultOf(d),
            result)

        action = LoggedAction.of_type(logger.messages, LOOP_UNTIL_ACTION)[0]
        assertContainsFields(self, action.start_message, {
            'predicate': predicate,
        })
        assertContainsFields(self, action.end_message, {
            'result': result,
        })
        self.assertTrue(action.succeeded)
        message = LoggedMessage.of_type(
            logger.messages, LOOP_UNTIL_ITERATION_MESSAGE)[0]
        self.assertEqual(action.children, [message])
        assertContainsFields(self, message.message, {
            'result': None,
        })

    @capture_logging(None)
    def test_multiple_iterations(self, logger):
        """
        If the predicate returns something falsey followed by something truthy,
        then ``loop_until`` returns it immediately.
        """
        result = object()
        results = [None, False, result]
        expected_results = results[:-1]

        def predicate():
            return results.pop(0)
        clock = Clock()

        d = loop_until(clock, predicate)

        clock.advance(0.1)
        self.assertNoResult(d)
        clock.advance(0.1)

        self.assertEqual(
            self.successResultOf(d),
            result)

        action = LoggedAction.of_type(logger.messages, LOOP_UNTIL_ACTION)[0]
        assertContainsFields(self, action.start_message, {
            'predicate': predicate,
        })
        assertContainsFields(self, action.end_message, {
            'result': result,
        })
        self.assertTrue(action.succeeded)
        messages = LoggedMessage.of_type(
            logger.messages, LOOP_UNTIL_ITERATION_MESSAGE)
        self.assertEqual(action.children, messages)
        self.assertEqual(
            [messages[0].message['result'], messages[1].message['result']],
            expected_results,
        )

    @capture_logging(None)
    def test_custom_time_steps(self, logger):
        """
        loop_until can be passed a generator of intervals to wait on.
        """
        result = object()
        results = [None, False, result]

        def predicate():
            return results.pop(0)
        clock = Clock()

        d = loop_until(clock, predicate, steps=[1, 2, 3])

        clock.advance(1)
        self.assertNoResult(d)
        clock.advance(1)
        self.assertNoResult(d)
        clock.advance(1)

        self.assertEqual(self.successResultOf(d), result)

    @capture_logging(None)
    def test_fewer_steps_than_repeats(self, logger):
        """
        loop_until can be given fewer steps than it needs for the predicate to
        return True. In that case, we raise ``LoopExceeded``.
        """
        results = [False] * 5
        steps = [0.1] * 2

        def predicate():
            return results.pop(0)
        clock = Clock()

        d = loop_until(clock, predicate, steps=steps)

        clock.advance(0.1)
        self.assertNoResult(d)
        clock.advance(0.1)
        self.assertEqual(
            str(self.failureResultOf(d).value),
            str(LoopExceeded(predicate, False)))


class RetryFailureTests(SynchronousTestCase):
    """
    Tests for :py:func:`retry_failure`.
    """

    def test_immediate_success(self):
        """
        If the function returns a successful value immediately, then
        ``retry_failure`` returns a deferred that has already fired with that
        value.
        """
        result = object()

        def function():
            return result

        clock = Clock()
        d = retry_failure(clock, function)
        self.assertEqual(self.successResultOf(d), result)

    def test_iterates_once(self):
        """
        If the function fails at first and then succeeds, ``retry_failure``
        returns the success.
        """
        steps = [0.1]

        result = object()
        results = [Failure(ValueError("bad value")), succeed(result)]

        def function():
            return results.pop(0)

        clock = Clock()

        d = retry_failure(clock, function, steps=steps)
        self.assertNoResult(d)

        clock.advance(0.1)
        self.assertEqual(self.successResultOf(d), result)

    def test_multiple_iterations(self):
        """
        If the function fails multiple times and then succeeds,
        ``retry_failure`` returns the success.
        """
        steps = [0.1, 0.2]

        result = object()
        results = [
            Failure(ValueError("bad value")),
            Failure(ValueError("bad value")),
            succeed(result),
        ]

        def function():
            return results.pop(0)

        clock = Clock()

        d = retry_failure(clock, function, steps=steps)
        self.assertNoResult(d)

        clock.advance(0.1)
        self.assertNoResult(d)

        clock.advance(0.1)
        self.assertNoResult(d)

        clock.advance(0.1)
        self.assertEqual(self.successResultOf(d), result)

    def test_too_many_iterations(self):
        """
        If ``retry_failure`` fails more times than there are steps provided, it
        errors back with the last failure.
        """
        steps = [0.1]

        result = object()
        failure = Failure(ValueError("really bad value"))

        results = [
            Failure(ValueError("bad value")),
            failure,
            succeed(result),
        ]

        def function():
            return results.pop(0)

        clock = Clock()

        d = retry_failure(clock, function, steps=steps)
        self.assertNoResult(d)

        clock.advance(0.1)
        self.assertEqual(self.failureResultOf(d), failure)

    def test_no_steps(self):
        """
        Calling ``retry_failure`` with an empty iterator for ``steps`` is the
        same as wrapping the function in ``maybeDeferred``.
        """
        steps = []

        result = object()
        failure = Failure(ValueError("really bad value"))

        results = [
            failure,
            succeed(result),
        ]

        def function():
            return results.pop(0)

        clock = Clock()

        d = retry_failure(clock, function, steps=steps)
        self.assertEqual(self.failureResultOf(d), failure)

    def test_limited_exceptions(self):
        """
        By default, ``retry_failure`` retries on any exception. However, if
        it's given an iterable of expected exception types (exactly as one
        might pass to ``Failure.check``), then it will only retry if one of
        *those* exceptions is raised.
        """
        steps = [0.1, 0.2]

        result = object()
        type_error = Failure(TypeError("bad type"))

        results = [
            Failure(ValueError("bad value")),
            type_error,
            succeed(result),
        ]

        def function():
            return results.pop(0)

        clock = Clock()

        d = retry_failure(clock, function, expected=[ValueError], steps=steps)
        self.assertNoResult(d)

        clock.advance(0.1)
        self.assertEqual(self.failureResultOf(d), type_error)


class PollUntilTests(SynchronousTestCase):
    """
    Tests for ``poll_until``.
    """

    def test_no_sleep_if_initially_true(self):
        """
        If the predicate starts off as True then we don't delay at all.
        """
        sleeps = []
        poll_until(lambda: True, repeat(1), sleeps.append)
        self.assertEqual([], sleeps)

    def test_polls_until_true(self):
        """
        The predicate is repeatedly call until the result is truthy, delaying
        by the interval each time.
        """
        sleeps = []
        results = [False, False, True]
        result = poll_until(lambda: results.pop(0), repeat(1), sleeps.append)
        self.assertEqual((True, [1, 1]), (result, sleeps))

    def test_default_sleep(self):
        """
        The ``poll_until`` function can be called with two arguments.
        """
        results = [False, True]
        result = poll_until(lambda: results.pop(0), repeat(0))
        self.assertEqual(True, result)

    def test_loop_exceeded(self):
        """
        If the iterable of intervals that we pass to ``poll_until`` is
        exhausted before we get a truthy return value, then we raise
        ``LoopExceeded``.
        """
        results = [False] * 5
        steps = [0.1] * 3
        self.assertRaises(
            LoopExceeded, poll_until, lambda: results.pop(0), steps,
            lambda ignored: None)

    def test_polls_one_last_time(self):
        """
        After intervals are exhausted, we poll one final time before
        abandoning.
        """
        # Three sleeps, one value to poll after the last sleep.
        results = [False, False, False, 42]
        steps = [0.1] * 3
        self.assertEqual(
            42,
            poll_until(lambda: results.pop(0), steps, lambda ignored: None))
