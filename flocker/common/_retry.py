# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Helpers for retrying things.
"""

from __future__ import absolute_import

from functools import partial
from inspect import getfile, getsourcelines
from itertools import repeat
import time

from eliot import ActionType, MessageType, Field
from eliot.twisted import DeferredContext

from twisted.python.reflect import safe_repr
from twisted.internet.task import deferLater
from twisted.internet.defer import maybeDeferred


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
