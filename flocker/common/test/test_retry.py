# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for ``flocker.common._retry``.
"""

from datetime import timedelta
from itertools import repeat, count
from functools import partial

from testtools.matchers import (
    MatchesPredicate, Is, Equals, AllMatch, IsInstance, GreaterThan, raises
)

from eliot import MessageType, fields
from eliot.testing import (
    capture_logging,
    LoggedAction, LoggedMessage,
    assertContainsFields, assertHasAction,
)

from twisted.internet.defer import succeed, fail, Deferred
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

from .. import (
    loop_until,
    retry_effect_with_timeout,
    retry_failure,
    poll_until,
    timeout,
    retry_if,
    get_default_retry_steps,
    decorate_methods,
    with_retry,
)
from .._retry import (
    LOOP_UNTIL_ACTION,
    LOOP_UNTIL_ITERATION_MESSAGE,
    LoopExceeded,
)
from ...testtools import TestCase, CustomException


class LoopUntilTests(TestCase):
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

    @capture_logging(None)
    def test_partial_predicate(self, logger):
        """
        Predicate can be a functools.partial function.
        """
        result = object()

        def check():
            return result
        predicate = partial(check)

        clock = Clock()
        d = loop_until(clock, predicate)
        self.assertEqual(
            self.successResultOf(d),
            result)

        [action] = LoggedAction.of_type(logger.messages, LOOP_UNTIL_ACTION)
        assertContainsFields(self, action.start_message, {
            'predicate': predicate,
        })
        assertContainsFields(self, action.end_message, {
            'action_status': 'succeeded',
            'result': result,
        })


class TimeoutTests(TestCase):
    """
    Tests for :py:func:`timeout`.
    """

    def setUp(self):
        """
        Initialize testing helper variables.
        """
        super(TimeoutTests, self).setUp()
        self.deferred = Deferred()
        self.timeout = 10.0
        self.clock = Clock()

    def test_doesnt_time_out_early(self):
        """
        A deferred that has not fired by some short while prior to the timeout
        interval is not made to fire with a timeout failure.
        """
        deferred = timeout(self.clock, self.deferred, self.timeout)
        self.clock.advance(self.timeout - 1.0)
        self.assertNoResult(deferred)

    def test_times_out(self):
        """
        A deferred that does not fire within the timeout interval is made to
        fire with ``CancelledError`` once the timeout interval elapses.
        """
        deferred = timeout(self.clock, self.deferred, self.timeout)
        self.clock.advance(self.timeout)
        self.failureResultOf(deferred, CancelledError)

    def test_times_out_with_reason(self):
        """
        If a custom reason is passed to ``timeout`` and the Deferred does not
        fire within the timeout interval, it is made to fire with the custom
        reason once the timeout interval elapses.
        """
        reason = CustomException(self.id())
        deferred = timeout(self.clock, self.deferred, self.timeout, reason)
        self.clock.advance(self.timeout)
        self.assertEqual(
            reason,
            self.failureResultOf(deferred, CustomException).value,
        )

    def test_doesnt_time_out(self):
        """
        A deferred that fires before the timeout is not cancelled by the
        timeout.
        """
        deferred = timeout(self.clock, self.deferred, self.timeout)
        self.clock.advance(self.timeout - 1.0)
        self.deferred.callback('Success')
        self.assertEqual(self.successResultOf(deferred), 'Success')

    def test_doesnt_time_out_failure(self):
        """
        A Deferred that fails before the timeout is not cancelled by the
        timeout.
        """
        deferred = timeout(self.clock, self.deferred, self.timeout)
        self.clock.advance(self.timeout - 1.0)
        self.deferred.errback(CustomException(self.id()))
        self.failureResultOf(deferred, CustomException)

    def test_doesnt_time_out_failure_custom_reason(self):
        """
        A Deferred that fails before the timeout is not cancelled by the
        timeout.
        """
        deferred = timeout(
            self.clock, self.deferred, self.timeout,
            ValueError("This should not appear.")
        )
        self.clock.advance(self.timeout - 1.0)
        self.deferred.errback(CustomException(self.id()))
        self.failureResultOf(deferred, CustomException)

    def test_advancing_after_success(self):
        """
        A Deferred that fires before the timeout continues to succeed after the
        timeout has elapsed.
        """
        deferred = succeed('Success')
        timeout(self.clock, deferred, self.timeout)
        self.clock.advance(self.timeout)
        self.assertEqual(self.successResultOf(deferred), 'Success')

    def test_advancing_after_failure(self):
        """
        A Deferred that fires with a failure before the timeout continues to
        fail after the timeout has elapsed.
        """
        deferred = fail(CustomException(self.id()))
        timeout(self.clock, deferred, self.timeout)
        self.clock.advance(self.timeout)
        self.failureResultOf(deferred, CustomException)

    def test_timeout_cleaned_up_on_success(self):
        """
        If the deferred is successfully completed before the timeout, the
        timeout is not still pending on the reactor.
        """
        timeout(self.clock, self.deferred, self.timeout)
        self.deferred.callback('Success')
        self.assertEqual(self.clock.getDelayedCalls(), [])

    def test_timeout_cleaned_up_on_failure(self):
        """
        If the deferred is failed before the timeout, the timeout is not still
        pending on the reactor.
        """
        timeout(self.clock, self.deferred, self.timeout)
        self.deferred.errback(CustomException(self.id()))
        # We need to handle the errback so that Trial and/or testtools don't
        # fail with unhandled errors.
        self.addCleanup(self.deferred.addErrback, lambda _: None)
        self.assertEqual(self.clock.getDelayedCalls(), [])


ITERATION_MESSAGE = MessageType("iteration_message", fields(iteration=int))


class RetryFailureTests(TestCase):
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

    def assert_logged_multiple_iterations(self, logger):
        """
        Function passed to ``retry_failure`` is run in the context of a
        ``LOOP_UNTIL_ACTION``.
        """
        iterations = LoggedMessage.of_type(logger.messages, ITERATION_MESSAGE)
        loop = assertHasAction(self, logger, LOOP_UNTIL_ACTION, True)
        self.assertEqual(
            sorted(iterations, key=lambda m: m.message["iteration"]),
            loop.children)

    @capture_logging(assert_logged_multiple_iterations)
    def test_multiple_iterations(self, logger):
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
            ITERATION_MESSAGE(iteration=(3 - len(results))).write()
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


class PollUntilTests(TestCase):
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


class RetryEffectTests(TestCase):
    """
    Tests for :py:func:`retry_effect_with_timeout`.
    """
    def get_time(self, times=None):
        if times is None:
            times = [1.0, 2.0, 3.0, 4.0, 5.0]

        def fake_time():
            return times.pop(0)
        return fake_time

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

    def test_timeout_measured_from_perform(self):
        """
        The timeout is measured from the time the effect is performed (not from
        the time it is created).
        """
        timeout = 3.0
        time = self.get_time([0.0] + list(timeout + i for i in range(10)))

        exceptions = [Exception("One problem")]
        result = object()

        def tester():
            if exceptions:
                raise exceptions.pop()
            return result

        retrier = retry_effect_with_timeout(
            Effect(Func(tester)),
            timeout=3,
            time=time,
        )

        # The retry effect has been created.  Advance time a little bit before
        # performing it.
        time()

        expected_intents = [
            # The first call raises an exception and should be retried even
            # though (as a side-effect of the `time` call above) the timeout,
            # as measured from when `retry_effect_with_timeout` was called, has
            # already elapsed.
            #
            # There's no second intent because the second call to the function
            # succeeds.
            (Delay(1), lambda ignore: None),
        ]
        self.assertThat(
            perform_sequence(expected_intents, retrier), Is(result)
        )


EXPECTED_RETRY_SOME_TIMES_RETRIES = 1200


class GetDefaultRetryStepsTests(TestCase):
    """
    Tests for ``get_default_retry_steps``.
    """
    def test_steps(self):
        """
        ``get_default_retry_steps`` returns an iterator consisting of the given
        delay repeated enough times to fill the given maximum time period.
        """
        delay = timedelta(seconds=3)
        max_time = timedelta(minutes=3)
        steps = list(get_default_retry_steps(delay, max_time))
        self.assertThat(set(steps), Equals({delay}))
        self.assertThat(sum(steps, timedelta()), Equals(max_time))

    def test_default(self):
        """
        There are default values for the delay and maximum time parameters
        accepted by ``get_default_retry_steps``.
        """
        steps = get_default_retry_steps()
        self.assertThat(steps, AllMatch(IsInstance(timedelta)))
        self.assertThat(steps, AllMatch(GreaterThan(timedelta())))


class RetryIfTests(TestCase):
    """
    Tests for ``retry_if``.
    """
    def test_matches(self):
        """
        If the matching function returns ``True``, the retry predicate returned
        by ``retry_if`` returns ``None``.
        """
        should_retry = retry_if(
            lambda exception: isinstance(exception, CustomException)
        )
        self.assertThat(
            should_retry(
                CustomException, CustomException("hello, world"), None
            ),
            Equals(None),
        )

    def test_does_not_match(self):
        """
        If the matching function returns ``False``, the retry predicate
        returned by ``retry_if`` re-raises the exception.
        """
        should_retry = retry_if(
            lambda exception: not isinstance(exception, CustomException)
        )
        self.assertThat(
            lambda: should_retry(
                CustomException, CustomException("hello, world"), None
            ),
            raises(CustomException),
        )


class DecorateMethodsTests(TestCase):
    """
    Tests for ``decorate_methods``.
    """
    @staticmethod
    def noop_wrapper(method):
        return method

    def test_data_descriptor(self):
        """
        Non-method attribute read access passes through to the wrapped object
        and the result is the same as if no wrapping had taken place.
        """
        class Original(object):
            class_attribute = object()

            def __init__(self):
                self.instance_attribute = object()

        original = Original()
        wrapper = decorate_methods(original, self.noop_wrapper)
        self.expectThat(
            wrapper.class_attribute,
            Equals(original.class_attribute),
        )
        self.expectThat(
            wrapper.instance_attribute,
            Equals(original.instance_attribute),
        )

    def test_passthrough(self):
        """
        Methods called on the wrapper have the same arguments passed through to
        the wrapped method and the result of the wrapped method returned if no
        exception is raised.
        """
        class Original(object):
            def some_method(self, a, b):
                return (b, a)

        a = object()
        b = object()

        wrapper = decorate_methods(Original(), self.noop_wrapper)
        self.expectThat(
            wrapper.some_method(a, b=b),
            Equals((b, a)),
        )


class WithRetryTests(TestCase):
    """
    Tests for ``with_retry``.
    """
    class AlwaysFail(object):
        failures = 0

        def some_method(self):
            self.failures += 1
            raise CustomException(self.failures)

    def always_failing(self, counter):
        raise CustomException(next(counter))

    def test_success(self):
        """
        If the wrapped method returns a value on the first call, the value is
        returned and no retries are made.
        """
        time = []
        sleep = time.append

        expected = object()
        another = object()
        results = [another, expected]

        wrapper = with_retry(results.pop, sleep=sleep)
        actual = wrapper()

        self.expectThat(actual, Equals(expected))
        self.expectThat(results, Equals([another]))

    def test_default_retry(self):
        """
        If no value is given for the ``should_retry`` parameter, if the wrapped
        method raises an exception it is called again after a short delay.
        This is repeated using the elements of ``retry_some_times`` as the
        sleep times and stops when there are no more elements.
        """
        time = []
        sleep = time.append

        counter = iter(count())
        wrapper = with_retry(
            partial(self.always_failing, counter), sleep=sleep
        )
        # XXX testtools ``raises`` helper generates a crummy message when this
        # assertion fails
        self.assertRaises(CustomException, wrapper)
        self.expectThat(
            next(counter),
            # The number of times we demonstrated (above) that retry_some_times
            # retries - plus one more for the initial call.
            Equals(EXPECTED_RETRY_SOME_TIMES_RETRIES + 1),
        )
        self.expectThat(
            sum(time),
            # Floating point maths.  Allow for some slop.
            MatchesPredicate(
                lambda t: 119.8 <= t <= 120.0,
                "Time value %r too far from expected value 119.9",
            ),
        )

    def test_steps(self):
        """
        If an iterator of steps is passed to ``with_retry``, it is used to
        determine the number of retries and the duration of the sleeps between
        retries.
        """
        s = timedelta(seconds=1)
        sleeps = []
        wrapper = with_retry(
            partial(self.always_failing, count()),
            sleep=sleeps.append,
            steps=[s * 1, s * 2, s * 3],
        )
        self.assertRaises(CustomException, wrapper)
        self.expectThat(sleeps, Equals([1, 2, 3]))

    def test_custom_should_retry(self):
        """
        If a predicate is passed for ``should_retry``, it used to determine
        whether a retry should be attempted any time an exception is raised.
        """
        counter = iter(count())
        original = partial(self.always_failing, counter)
        wrapped = with_retry(
            original,
            should_retry=retry_if(
                lambda exception: (
                    isinstance(exception, CustomException) and
                    exception.args[0] < 10
                ),
            ),
            sleep=lambda interval: None,
        )

        self.expectThat(wrapped, raises(CustomException))
        self.expectThat(next(counter), Equals(11))
