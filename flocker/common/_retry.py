# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Helpers for retrying things.
"""

from __future__ import absolute_import, division

from sys import exc_info
from time import sleep

from datetime import timedelta
from functools import partial
from inspect import getfile, getsourcelines
from itertools import repeat
import time

from eliot import (
    ActionType, MessageType, Message, Field, start_action, write_traceback,
)
from eliot.twisted import DeferredContext

from twisted.python.reflect import safe_repr
from twisted.internet.task import deferLater
from twisted.internet.defer import maybeDeferred
from twisted.python.reflect import fullyQualifiedName

from effect import Effect, Constant, Delay
from effect.retry import retry


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


def timeout(reactor, deferred, timeout_sec):
    """Adds a timeout to an existing deferred. If the timeout expires before
    the deferred expires, then the deferred is cancelled.

    :param IReactorTime reactor: The reactor implementation to schedule the
        timeout.

    :param Deferred deferred: The deferred to cancel at a later point in time.

    :param float timeout_sec: The number of seconds to wait before the deferred
        should time out.
    """
    def _timeout():
        deferred.cancel()

    delayed_timeout = reactor.callLater(timeout_sec, _timeout)

    def abort_timeout(passthrough):
        if delayed_timeout.active():
            delayed_timeout.cancel()
        return passthrough
    deferred.addBoth(abort_timeout)


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

    d = maybeDeferred(function)

    def loop(failure):
        if expected and not failure.check(*expected):
            return failure

        try:
            interval = steps.next()
        except StopIteration:
            return failure

        d = deferLater(reactor, interval, function)
        d.addErrback(loop)
        return d

    d.addErrback(loop)

    return d


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
    :param int timeout: Keep retrying until timeout.
    :param timedelta retry_wait: The wait time between retries
    :param bool backoff: Whether we should use exponential backoff
    :param callable time: A nullary callable that returns a UNIX timestamp.

    :return: An Effect that does what ``effect`` does, but retrying on
        exception.
    """
    end_time = time() + timeout

    def should_retry(e):
        if time() >= end_time:
            return Effect(Constant(False))
        else:
            retry_delay = should_retry.wait_secs.total_seconds()
            effect = Effect(Delay(retry_delay)).on(
                success=lambda x: Effect(Constant(True))
            )

            if backoff:
                should_retry.wait_secs *= 2

            return effect

    should_retry.wait_secs = retry_wait

    return retry(effect, should_retry)


_TRY_UNTIL_SUCCESS = u"flocker:failure-retry"
_TRY_RETRYING = _TRY_UNTIL_SUCCESS + u":retrying"
_TRY_FAILURE = _TRY_UNTIL_SUCCESS + u":failure"
_TRY_SUCCESS = _TRY_UNTIL_SUCCESS + u":success"


def retry_on_intervals(intervals):
    """
    Create a predicate compatible with ``wrap_methods_with_failure_retry``
    which will retry with exactly the given delays in between.
    """
    intervals = iter(intervals)

    def should_retry(exc_type, value, traceback):
        for interval in intervals:
            # Log any failure we're retrying
            write_traceback()
            return interval
        # Out of steps, fail the retry loop overall.
        raise exc_type, value, traceback
    return should_retry


def retry_some_times():
    """
    Create a predicate compatible with ``wrap_methods_with_failure_retry``
    which will retry a fixed number of times with a brief delay in between.
    """
    delay = 0.1
    timeout = 120.0
    times = int(timeout // delay)
    steps = repeat(timedelta(seconds=delay), times)

    return retry_on_intervals(steps)


def retry_if(predicate):
    """
    Create a predicate compatible with ``wrap_methods_with_failure_retry``
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


def compose_retry(should_retries):
    """
    Combine several retry predicates by applying them in series.

    The predicates are tested in the order given.  If a predicate raises an
    exception, processing stops and no retry is attempted.  If a predicate
    returns ``None``, processing continues to the next predicate.  If it
    returns a ``timedelta``, processing stops and a retry is attempted after a
    delay of that length.

    :param list should_retries: The retry predicates to apply.

    :return: A single retry predicate which is composed of ``should_retries``.
    """
    def composed(exc_type, value, traceback):
        for should_retry in should_retries:
            result = should_retry(exc_type, value, traceback)
            if result is not None:
                return result
        return None
    return composed


def decorate_methods(obj, decorator):
    """
    Return a wrapper around ``obj`` with ``decorator`` applied to all of its
    method calls.

    :param callable decorator: A unary callable that takes a method and
        returns a method.

    :return: An object like ``obj`` but with all the methods decorated.
    """
    return _DecoratedInstance(obj, decorator)


def _poll_until_success_returning_result(
    should_retry, sleep, function, args, kwargs
):
    """
    Call a function until it does not raise an exception or ``should_retry``
    says it shouldn't be tried anymore, whichever comes first.

    :param should_retry: A three-argument callable which determines whether
        further retries are attempted.  If ``None`` or a ``timedelta`` is
        returned, another retry is attempted (immediately or after sleeping for
        the indicated interval, respectively).  If an exception is raised,
        further tries are not attempted and the exception is allowed to
        propagate.
    :param sleep: A function like ``time.sleep`` to use for the delays.
    :param function: The function to try calling.
    :param args: Position arguments to pass to the function.
    :param kwargs: Keyword arguments to pass to the function.

    :return: The value returned by ``function`` on the first call where it
        returns a value instead of raising an exception.
    """
    saved_result = []

    def pollable():
        Message.new(
            message_type=_TRY_RETRYING,
        ).write()
        try:
            result = function(*args, **kwargs)
        except Exception as e:
            delay = should_retry(*exc_info())
            Message.new(
                message_type=_TRY_FAILURE,
                exception=str(e),
            ).write()
            if delay is not None:
                sleep(delay.total_seconds())
            return False
        else:
            Message.new(
                message_type=_TRY_SUCCESS,
                result=result,
            ).write()
            saved_result.append(result)
            return True

    poll_until(pollable, repeat(0.0), sleep=sleep)

    return saved_result[0]


def with_retry(method, should_retry=None, sleep=None):
    if should_retry is None:
        should_retry = retry_some_times()
    def method_with_retry(*a, **kw):
        name = fullyQualifiedName(method)
        action_type = _TRY_UNTIL_SUCCESS
        with start_action(action_type=action_type, function=name):
            return _poll_until_success_returning_result(
                should_retry, sleep, method, a, kw
            )
    return method_with_retry


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
