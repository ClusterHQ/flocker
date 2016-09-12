# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Helpers for retrying things.
"""

from __future__ import absolute_import, division

from sys import exc_info

from datetime import timedelta
from functools import partial
from inspect import getfile, getsourcelines
from itertools import chain, count, imap, repeat, takewhile
from random import uniform
import time

from eliot import (
    ActionType, MessageType, Message, Field, start_action,
)
from eliot.twisted import DeferredContext

from twisted.python.reflect import fullyQualifiedName, safe_repr
from twisted.python.failure import Failure
from twisted.internet.task import deferLater
from twisted.internet.defer import maybeDeferred

from effect import Effect, Constant, Delay
from effect.retry import retry


def backoff(step=5.0, maximum_step=60.0, timeout=10*60.0, jitter=0.2):
    """
    Generate increasingly large values for use as the ``steps`` argument to
    retry functions.

    :param float step: The amount by which to increase successive values.
    :param float maximum_step: The maximum value that will be
        generated. ``None`` means no maximum.
    :param float timeout: No further values will be generated when the sum of
        the generated steps is greater than ``timeout``. ``None`` means no
        timeout.
    :param float jitter: If not ``None``, the generated values will be adjusted
        by a random amount between +/- ``jitter.
    :returns: A generator of floats.
    """
    if step <= 0.0:
        raise ValueError("Invalid ``step`` ({!r}). "
                         "Must be > 0.0.".format(step))
    steps = imap(
        lambda x: x * step,
        count(start=1)
    )
    if maximum_step is not None:
        if maximum_step <= 0.0:
            raise ValueError(
                "Invalid ``maximum_step`` ({!r}). "
                "Must be > 0.0.".format(
                    maximum_step
                )
            )

        steps = takewhile(
            lambda x: x < maximum_step,
            steps
        )
        steps = chain(
            steps,
            repeat(maximum_step)
        )
    if jitter is not None:
        steps = imap(
            lambda x: x + uniform(-jitter, jitter),
            steps,
        )
    if timeout is not None:
        total_time = [0]

        def maybe_timeout(values):
            for value in values:
                total_time[0] += value
                if total_time[0] > timeout:
                    break
                yield value

        steps = maybe_timeout(steps)

    return steps


def function_serializer(function):
    """
    Serialize the given function for logging by eliot.

    :param function: Function to serialize.

    :return: Serialized version of function for inclusion in logs.
    """
    try:
        return {
            "function": str(function),
            "file": getfile(function),
            "line": getsourcelines(function)[1]
        }
    except IOError:
        # One debugging method involves changing .py files and is incompatible
        # with inspecting the source.
        return {
            "function": str(function),
        }
    except TypeError:
        # Callable not supported by inspect.getfile
        if isinstance(function, partial):
            return {
                'partial': function_serializer(function.func)
            }
        else:
            return {
                "function": str(function),
            }


class LoopExceeded(Exception):
    """
    Raised when ``loop_until`` looped too many times.
    """

    def __init__(self, predicate, last_result):
        super(LoopExceeded, self).__init__(
            '%r never True in loop_until, last result: %r'
            % (predicate, last_result))


LOOP_UNTIL_ACTION = ActionType(
    action_type="flocker:common:loop_until",
    startFields=[Field("predicate", function_serializer)],
    successFields=[Field("result", serializer=safe_repr)],
    description="Looping until predicate is true.")

LOOP_UNTIL_ITERATION_MESSAGE = MessageType(
    message_type="flocker:common:loop_until:iteration",
    fields=[Field("result", serializer=safe_repr)],
    description="Predicate failed, trying again.")


def loop_until(reactor, predicate, steps=None):
    """Repeatedly call ``predicate``, until it returns something ``Truthy``.

    :param reactor: The reactor implementation to use to delay.
    :type reactor: ``IReactorTime``.

    :param predicate: Callable returning termination condition.
    :type predicate: 0-argument callable returning a Deferred.

    :param steps: An iterable of delay intervals, measured in seconds.
        If not provided, will default to retrying every 0.1 seconds forever.

    :raise LoopExceeded: If given a finite sequence of steps, and we exhaust
        that sequence waiting for predicate to be truthy.

    :return: A ``Deferred`` firing with the first ``Truthy`` response from
        ``predicate``.
    """
    if steps is None:
        steps = repeat(0.1)
    steps = iter(steps)

    action = LOOP_UNTIL_ACTION(predicate=predicate)

    d = action.run(DeferredContext, maybeDeferred(action.run, predicate))

    def loop(result):
        if not result:
            LOOP_UNTIL_ITERATION_MESSAGE(
                result=result
            ).write()
            try:
                delay = steps.next()
            except StopIteration:
                raise LoopExceeded(predicate, result)
            d = deferLater(reactor, delay, action.run, predicate)
            d.addCallback(partial(action.run, loop))
            return d
        action.addSuccessFields(result=result)
        return result
    d.addCallback(loop)
    return d.addActionFinish()


def timeout(reactor, deferred, timeout_sec, reason=None):
    """
    Adds a timeout to an existing deferred.  If the timeout expires before the
    deferred expires, then the deferred is cancelled.

    :param IReactorTime reactor: The reactor implementation to schedule the
        timeout.
    :param Deferred deferred: The deferred to cancel at a later point in time.
    :param float timeout_sec: The number of seconds to wait before the deferred
        should time out.
    :param Exception reason: An exception used to create a Failure with which
        to fire the Deferred if the timeout is encountered.  If not given,
        ``deferred`` retains its original failure behavior.

    :return: The updated deferred.
    """
    def _timeout():
        deferred.cancel()

    delayed_timeout = reactor.callLater(timeout_sec, _timeout)

    if reason is not None:
        def maybe_replace_reason(passthrough):
            if delayed_timeout.active():
                return passthrough
            return Failure(reason)
        deferred.addErrback(maybe_replace_reason)

    def abort_timeout(passthrough):
        if delayed_timeout.active():
            delayed_timeout.cancel()
        return passthrough
    deferred.addBoth(abort_timeout)

    return deferred


def retry_failure(reactor, function, expected=None, steps=None):
    """
    Retry ``function`` until it returns successfully.

    If it raises one of the expected exceptions, then retry.

    :param IReactorTime reactor: The reactor implementation to use to delay.
    :param callable function: A callable that returns a value.
    :param expected: Iterable of exceptions that trigger a retry. Passed
        through to ``Failure.check``.
    :param [float] steps: An iterable of delay intervals, measured in seconds.
        If not provided, will default to retrying every 0.1 seconds.

    :return: A ``Deferred`` that fires with the first successful return value
        of ``function``.
    """
    if steps is None:
        steps = repeat(0.1)
    steps = iter(steps)

    action = LOOP_UNTIL_ACTION(predicate=function)
    with action.context():
        d = DeferredContext(maybeDeferred(function))

    def loop(failure):
        if expected and not failure.check(*expected):
            return failure

        try:
            interval = steps.next()
        except StopIteration:
            return failure

        d = deferLater(reactor, interval, action.run, function)
        d.addErrback(loop)
        return d

    d.addErrback(loop)

    def got_result(result):
        action.add_success_fields(result=result)
        return result
    d.addCallback(got_result)
    d.addActionFinish()
    return d.result


def poll_until(predicate, steps, sleep=None):
    """
    Perform steps until a non-false result is returned.

    This differs from ``loop_until`` in that it does not require a
    Twisted reactor.

    :param predicate: a function to be called until it returns a
        non-false result.
    :param [float] steps: An iterable of delay intervals, measured in seconds.
    :param callable sleep: called with the interval to delay on.
        Defaults to `time.sleep`.
    :returns: the non-false result from the final call.
    :raise LoopExceeded: If given a finite sequence of steps, and we exhaust
        that sequence waiting for predicate to be truthy.
    """
    if sleep is None:
        sleep = time.sleep
    for step in steps:
        result = predicate()
        if result:
            return result
        sleep(step)
    result = predicate()
    if result:
        return result
    raise LoopExceeded(predicate, result)


# TODO: Would be nice if this interface were more similar to some of the other
# retry functions in this module.  For example, accept an iterable of intervals
# instead of timeout/retry_wait/backoff.
def retry_effect_with_timeout(effect, timeout, retry_wait=timedelta(seconds=1),
                              backoff=True, time=time.time):
    """
    If ``effect`` fails, retry it until ``timeout`` expires.

    To avoid excessive retrying, this function uses the exponential backoff
    algorithm by default, waiting double the time between each retry.

    :param Effect effect: The Effect to retry.
    :param int timeout: Keep retrying until timeout.  This is measured in
        seconds from the time of the first failure of ``effect``.
    :param timedelta retry_wait: The wait time between retries
    :param bool backoff: Whether we should use exponential backoff
    :param callable time: A nullary callable that returns a UNIX timestamp.

    :return: An Effect that does what ``effect`` does, but retrying on
        exception.
    """
    class State(object):
        end_time = None
        wait_time = None

    def should_retry(exc_info):
        # This is the wrong time to compute end_time.  It's a lot simpler to do
        # this than to hook into the effect being wrapped and record the time
        # it starts to run.  Perhaps implementing that would be a nice thing to
        # do later.
        #
        # Anyway, make note of when we want to be finished if we haven't yet
        # done so.
        if State.end_time is None:
            State.end_time = time() + timeout

        if time() >= State.end_time:
            return Effect(Constant(False))
        else:
            retry_delay = State.wait_time.total_seconds()
            effect = Effect(Delay(retry_delay)).on(
                success=lambda x: Effect(Constant(True))
            )

            if backoff:
                State.wait_time *= 2

            return effect

    State.wait_time = retry_wait

    return retry(effect, should_retry)


_TRY_UNTIL_SUCCESS = u"flocker:failure-retry"
_TRY_RETRYING = _TRY_UNTIL_SUCCESS + u":retrying"
_TRY_FAILURE = _TRY_UNTIL_SUCCESS + u":failure"
_TRY_SUCCESS = _TRY_UNTIL_SUCCESS + u":success"


def get_default_retry_steps(
    delay=timedelta(seconds=0.1),
    max_time=timedelta(minutes=2)
):
    """
    Retry every 0.1 seconds for 2 minutes.
    """
    repetitions = max_time.total_seconds() / delay.total_seconds()
    return repeat(delay, int(repetitions))


def retry_always(exc_type, value, traceback):
    pass


def retry_if(predicate):
    """
    Create a predicate compatible with ``with_retry``
    which will retry if the raised exception satisfies the given predicate.

    :param predicate: A one-argument callable which will be called with the
        raised exception instance only.  It should return ``True`` if a retry
        should be attempted, ``False`` otherwise.
    """
    def should_retry(exc_type, value, traceback):
        if predicate(value):
            return None
        raise exc_type, value, traceback
    return should_retry


# TODO Move this helper to somewhere else in flocker.common.  It's not
# particular to any retry logic.
def decorate_methods(obj, decorator):
    """
    Return a wrapper around ``obj`` with ``decorator`` applied to all of its
    method calls.

    For example, to retry on IOError up to 5 times with a 3 second delay
    between each try::

        retry_three_times = partial(
            with_retry,
            should_retry=retry_if(lambda exc: isinstance(exc, IOError)),
            steps=[timedelta(seconds=3)] * 5,
        )
        obj_with_three_retries = decorate_methods(obj, retry_three_times)

    :param callable decorator: A unary callable that takes a method and returns
        a method.

    :return: An object like ``obj`` but with all the methods decorated.
    """
    return _DecoratedInstance(obj, decorator)


def _poll_until_success_returning_result(
    should_retry, steps, sleep, function, args, kwargs
):
    """
    Call a function until it does not raise an exception or ``should_retry``
    says it shouldn't be tried anymore, whichever comes first.

    :param should_retry: See ``should_retry`` parameter of ``with_retry``.
    :param steps: See ``steps`` parameter of ``with_retry``.
    :param sleep: See ``sleep`` parameter of ``with_retry``.
    :param function: The function to try calling.
    :param args: Position arguments to pass to the function.
    :param kwargs: Keyword arguments to pass to the function.

    :return: The value returned by ``function`` on the first call where it
        returns a value instead of raising an exception.
    """
    saved_result = [None]

    def pollable():
        Message.new(
            message_type=_TRY_RETRYING,
        ).write()
        try:
            result = function(*args, **kwargs)
        except Exception as e:
            saved_result[0] = exc_info()
            should_retry(*saved_result[0])
            Message.new(
                message_type=_TRY_FAILURE,
                exception=str(e),
            ).write()
            return False
        else:
            Message.new(
                message_type=_TRY_SUCCESS,
                result=result,
            ).write()
            saved_result[0] = result
            return True

    try:
        poll_until(
            pollable, (step.total_seconds() for step in steps), sleep=sleep,
        )
    except LoopExceeded:
        # XXX untested
        thing = saved_result.pop()
        try:
            raise thing[0], thing[1], thing[2]
        finally:
            del thing
    else:
        return saved_result[0]


def with_retry(method, should_retry=None, steps=None, sleep=None):
    """
    Return a new version of ``method`` that retries.

    :param callable method: A method to retry.
    :param callable should_retry: A one-argument callable which accepts a
        three-tuple of exception state and returns ``None`` or raises an
        exception.  If ``None`` is returned, the call will be retried after a
        delay given by the next element of ``steps``.  If an exception is
        raised, no further retries are attempted and the exception is
        propagated from the method call.
    :param steps: An iterator of delay intervals (as ``timedelta`` instances).
        These intervals give the amount of time to wait between retries.
    :param callable sleep: A replacement for ``time.sleep``.

    :return: A method that will retry.
    """
    if should_retry is None:
        should_retry = retry_always

    if steps is None:
        steps = get_default_retry_steps()

    def method_with_retry(*a, **kw):
        name = _callable_repr(method)
        action_type = _TRY_UNTIL_SUCCESS
        with start_action(action_type=action_type, function=name):
            return _poll_until_success_returning_result(
                should_retry, steps, sleep, method, a, kw
            )
    return method_with_retry


def _callable_repr(method):
    """Get a useful representation ``method``."""
    try:
        return fullyQualifiedName(method)
    except AttributeError:
        return safe_repr(method)


class _DecoratedInstance(object):
    def __init__(self, wrapped, decorator, **kw):
        self._wrapped = wrapped
        self._decorator = decorator
        self._kw = kw

    def __getattr__(self, name):
        attribute = getattr(self._wrapped, name)
        if callable(attribute):
            return self._decorator(attribute, **self._kw)
        return attribute
