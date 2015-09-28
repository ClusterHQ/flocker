# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
# -*- test-case-name: flocker.node.test.test_deploy -*-

"""
Various helpers for dealing with Deferred APIs in flocker.
"""

from twisted.internet.defer import Deferred, gatherResults, maybeDeferred
from twisted.python import log

from ._interface import interface_decorator


def gather_deferreds(deferreds):
    """
    Return a ``Deferred`` which fires when all of the supplied
    ``deferreds`` have themselves fired.

    Any errback in the supplied ``deferreds`` will be handled and logged
    with a call to ``twisted.python.log.err``.

    See ``twisted.internet.defer.gatherResults`` which this function wraps.

    :param list deferreds: A ``list`` of ``Deferred``\ s whose results will
        be gathered.
    :returns: A ``Deferred`` which fires only when all the supplied
        ``deferreds`` have fired. If all the supplied ``deferreds`` succeed the
        result will callback with a ``list`` of all the results.  If any of the
        supplied ``deferreds`` fail, the result will errback with a
        ``FirstError`` failure containing a reference to the failure produced
        by the first of the ``deferreds`` to fail.
    """
    # Gather once to get the results OR the first failure
    results_or_first_failure = gatherResults(deferreds)

    def log_and_discard(failure):
        """
        Log the supplied failure and discard it.

        The failure is deliberately discarded so as to prevent any further
        logging of this failure when the deferred is eventually garbage
        collected.

        :param Failure failure: The ``Failure`` to be logged.
        """
        log.err(failure)

    for deferred in deferreds:
        deferred.addErrback(log_and_discard)

    # After adding logging callbacks, gather again so as to wait for all
    # the supplied deferreds to fire.
    gathering = gatherResults(deferreds)

    # Then return the result of the first gather.
    gathering.addCallback(lambda ignored: results_or_first_failure)
    return gathering


class EventChannel(object):
    """
    An L{EventChannel} provides one-to-many event publishing in a
    re-usable container.

    Any number of parties may subscribe to an event channel to receive
    the very next event published over it.  A subscription is a
    L{Deferred} which will get the next result and is then no longer
    associated with the L{EventChannel} in any way.

    Future events can be received by re-subscribing to the channel.

    @ivar _subscriptions: A L{list} of L{Deferred} instances which are waiting
        for the next event.
    """
    def __init__(self):
        self._subscriptions = []

    def _itersubscriptions(self):
        """
        Return an iterator over all current subscriptions after
        resetting internal subscription state to forget about all of
        them.
        """
        subscriptions = self._subscriptions[:]
        del self._subscriptions[:]
        return iter(subscriptions)

    def callback(self, value):
        """
        Supply a success value for the next event which will be published now.
        """
        for subscr in self._itersubscriptions():
            subscr.callback(value)

    def errback(self, reason=None):
        """
        Supply a failure value for the next event which will be published now.
        """
        for subscr in self._itersubscriptions():
            subscr.errback(reason)

    def subscribe(self):
        """
        Get a L{Deferred} which will fire with the next event on this channel.

        @rtype: L{Deferred}
        """
        d = Deferred(canceller=self._subscriptions.remove)
        self._subscriptions.append(d)
        return d


def methods_once_at_a_time(interface, original_name):
    return interface_decorator(
        "once_upon_a_time",
        interface,
        _run_once_at_a_time_method,
        original_name,
    )


def _run_once_at_a_time_method(method_name, original_name):
    def _run_once_at_a_time(self, *args, **kwargs):
        try:
            cache = self._once_at_a_time_cache
        except AttributeError:
            cache = self._once_at_a_time_cache = {}
        try:
            state = cache[method_name]
        except KeyError:
            state = cache[method_name] = OnceAtATime()

        # Look up the method each time instead of saving it on the _OnceCache
        # to avoid automatically building a circular reference.
        original_self = getattr(self, original_name)
        original_method = getattr(original_self, method_name)
        return state.run(original_method, args, kwargs)

    return _run_once_at_a_time


class OnceAtATime(object):
    _call = None
    _next = None

    def run(self, method, args=(), kwargs=None):
        if kwargs is None:
            kwargs = {}

        if self._call is None:
            # No call is active.  Start one.
            self._call = _Call(method, args, kwargs)
            return self._go()

        # Set up the next call to match the given arguments.
        new_next = _Call(method, args, kwargs)

        if self._next is not None:
            # A next call is already planned.  Publish the result of the new
            # next call to anyone waiting on the result of the old next call.
            # The old next call will never actually run so this is where its
            # results will come from.
            new_next.result().addBoth(self._next.complete)

        # Save the next call for eventual execution.
        self._next = new_next

        # Give the caller a Deferred that will fire with the result of the next
        # call (or the call that replaces it).
        return self._next.result()

    def _go(self):
        self._call.result().addBoth(self._continue)
        result = self._call.result()
        self._call.go()
        return result

    def _continue(self, ignored):
        # A call finished.
        self._call = None
        # If there is a next call, start it.
        if self._next is not None:
            self._call = self._next
            self._next = None
            self._go()


class _Call(object):
    def __init__(self, method, args, kwargs):
        self.method = method
        self.args = args
        self.kwargs = kwargs
        self._channel = EventChannel()

    def result(self):
        return self._channel.subscribe()

    def go(self):
        d = maybeDeferred(self.method, *self.args, **self.kwargs)
        d.addBoth(self.complete)

    def complete(self, result):
        self._channel.callback(result)
