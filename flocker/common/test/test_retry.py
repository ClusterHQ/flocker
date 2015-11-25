# Copyright ClusterHQ Ltd.  See LICENSE file for details.

"""
Tests for ``flocker.common._retry``.
"""

from datetime import timedelta
from itertools import repeat

from eliot.testing import (
    capture_logging,
    LoggedAction, LoggedMessage,
    assertContainsFields,
)

from twisted.internet.defer import succeed, Deferred
from twisted.trial.unittest import SynchronousTestCase
from twisted.internet.defer import CancelledError
from twisted.internet.task import Clock
from twisted.python.failure import Failure

from effect import (
    Effect,
    Func,
    Constant,
    Delay,
)
from effect.testing import perform_sequence

from .._retry import (
    LOOP_UNTIL_ACTION,
    LOOP_UNTIL_ITERATION_MESSAGE,
    LoopExceeded,
    loop_until,
    retry_effect_with_timeout,
    retry_failure,
    poll_until,
    timeout,
)
from ...testtools import CustomException


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


class TimeoutTests(SynchronousTestCase):
    """
    Tests for :py:func:`timeout`.
    """

    def setUp(self):
        """Initialize testing helper variables."""
        self._deferred = Deferred()
        self._timeout = 1.0
        self._clock = Clock()

    def _trapError(self, error_type):
        """Assert a deferred has a result of a specific error and trap it."""
        self._deferred.result.trap(error_type)

        def errback(e):
            e.trap(error_type)
            return None
        self._deferred.addErrback(error_type)

    def _execute_timeout(self):
        """Execute the timeout."""
        timeout(self._clock, self._deferred, self._timeout)

    def test_times_out(self):
        """
        A deferred that never fires is timed out at the correct time using the
        timeout function, and concludes with a CancelledError failure.
        """
        self._execute_timeout()
        self._clock.advance(self._timeout - 0.1)
        self.assertFalse(self._deferred.called)
        self._clock.advance(0.1)
        self.assertTrue(self._deferred.called)
        self._trapError(CancelledError)

    def test_doesnt_time_out(self):
        """
        A deferred that fires before the timeout is not cancelled by the
        timeout.
        """
        self._execute_timeout()
        self._clock.advance(self._timeout - 0.1)
        self.assertFalse(self._deferred.called)
        self._deferred.callback('Success')
        self.assertTrue(self._deferred.called)
        self.assertEqual(self._deferred.result, 'Success')
        self._clock.advance(0.1)
        self.assertTrue(self._deferred.called)
        self.assertEqual(self._deferred.result, 'Success')

    def test_timeout_cleaned_up_on_success(self):
        """
        If the deferred is successfully completed before the timeout, the
        timeout is not still pending on the reactor.
        """
        self._execute_timeout()
        self._clock.advance(self._timeout - 0.1)
        self._deferred.callback('Success')
        self.assertEqual(self._clock.getDelayedCalls(), [])
        self.assertEqual(self._deferred.result, 'Success')

    def test_timeout_cleaned_up_on_failure(self):
        """
        If the deferred is failed before the timeout, the timeout is not still
        pending on the reactor.
        """
        self._execute_timeout()
        self._clock.advance(self._timeout - 0.1)
        self._deferred.errback(Exception('ErrorXYZ'))
        self.assertEqual(self._clock.getDelayedCalls(), [])
        self.assertEqual(self._deferred.result.getErrorMessage(), 'ErrorXYZ')
        self._trapError(Exception)


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


class RetryEffectTests(SynchronousTestCase):
    """
    Tests for :py:func:`retry_effect_with_timeout`.
    """
    def get_time(self, times=None):
        if times is None:
            times = [1.0, 2.0, 3.0, 4.0, 5.0]
        return lambda: times.pop(0)

    def test_immediate_success(self):
        """
        If the wrapped effect succeeds at first, no delay or retry is done and
        the retry effect's result is the wrapped effect's result.
        """
        effect = Effect(Constant(1000))
        retrier = retry_effect_with_timeout(effect, 10, time=self.get_time())
        result = perform_sequence([], retrier)
        self.assertEqual(result, 1000)

    def test_one_retry(self):
        """
        Retry the effect if it fails once.
        """
        divisors = [0, 1]

        def tester():
            x = divisors.pop(0)
            return 1 / x

        seq = [
            (Delay(1), lambda ignore: None),
        ]

        retrier = retry_effect_with_timeout(Effect(Func(tester)), 10,
                                            time=self.get_time())
        result = perform_sequence(seq, retrier)
        self.assertEqual(result, 1 / 1)

    def test_exponential_backoff(self):
        """
        Retry the effect multiple times with exponential backoff between
        retries.
        """
        divisors = [0, 0, 0, 1]

        def tester():
            x = divisors.pop(0)
            return 1 / x

        seq = [
            (Delay(1), lambda ignore: None),
            (Delay(2), lambda ignore: None),
            (Delay(4), lambda ignore: None),
        ]

        retrier = retry_effect_with_timeout(
            Effect(Func(tester)), timeout=10, time=self.get_time(),
        )
        result = perform_sequence(seq, retrier)
        self.assertEqual(result, 1)

    def test_no_exponential_backoff(self):
        """
        If ``False`` is passed for the ``backoff`` parameter, the effect is
        always retried with the same delay.
        """
        divisors = [0, 0, 0, 1]

        def tester():
            x = divisors.pop(0)
            return 1 / x

        seq = [
            (Delay(5), lambda ignore: None),
            (Delay(5), lambda ignore: None),
            (Delay(5), lambda ignore: None),
        ]

        retrier = retry_effect_with_timeout(
            Effect(Func(tester)), timeout=1, retry_wait=timedelta(seconds=5),
            backoff=False,
        )
        result = perform_sequence(seq, retrier)
        self.assertEqual(result, 1)

    def test_timeout(self):
        """
        If the timeout expires, the retry effect fails with the exception from
        the final time the wrapped effect is performed.
        """
        expected_intents = [
            (Delay(1), lambda ignore: None),
            (Delay(2), lambda ignore: None),
        ]

        exceptions = [
            Exception("Wrong (1)"),
            Exception("Wrong (2)"),
            CustomException(),
        ]

        def tester():
            raise exceptions.pop(0)

        retrier = retry_effect_with_timeout(
            Effect(Func(tester)),
            timeout=3,
            time=self.get_time([0.0, 1.0, 2.0, 3.0, 4.0, 5.0]),
        )

        self.assertRaises(
            CustomException,
            perform_sequence, expected_intents, retrier
        )
