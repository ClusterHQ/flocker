# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Generally helpful tools.
"""

__all__ = ["EventChannel", "UnCooperator"]

from twisted.internet.defer import Deferred, succeed


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



class _MinimallyCooperativeTask(object):
    """
    @ivar _done: C{False} until iteration over the iterator has gone past the
        last element.  C{True} afterwards.
    @type _done: L{bool}

    @ivar _result: C{None} until C{_done} is C{True}.  Afterwards, the last
        element of the iterator (or if the last element was a L{Deferred}, the
        result of that L{Deferred}).

    @ivar _channel: Used to give out results from C{whenDone}.  Fires with just
        one event (when the iterator is exhausted).
    @type _channel: L{EventChannel}
    """
    def __init__(self, iterator):
        """
        @param iterator: The iterator to exhaust.
        """
        self._done = False
        self._result = None
        self._channel = EventChannel()
        self._channel.subscribe().addBoth(self._setResult)
        self._sequentially(iterator).addCallbacks(
            self._channel.callback, self._channel.errback)


    def _setResult(self, result):
        """
        Mark the task as complete and record its result.
        """
        self._done = True
        self._result = result


    def whenDone(self):
        """
        Get a L{Deferred} that fires with the result of this task.
        """
        if self._done:
            return succeed(self._result)
        else:
            return self._channel.subscribe()


    @classmethod
    def _sequentially(cls, iterator):
        """
        Begin iterating over C{iterator}.

        Iteration is done as quickly as possible.  It is only interrupted when
        a L{Deferred} without a result is encountered.  Then iteration is
        suspended until that L{Deferred} has a result.
        """
        finished = Deferred()
        cls._iteration(finished, iterator)
        return finished


    @classmethod
    def _iteration(cls, finished, iterator, result=None):
        """
        Iterate over C{iterator} until a L{Deferred} is encountered.
        """
        while True:
            try:
                waiting = next(iterator)
            except StopIteration:
                finished.callback(result)
                break
            except:
                finished.errback()
                break
            else:
                if isinstance(waiting, Deferred):
                    waiting.addCallbacks(
                        lambda result:
                            cls._iteration(finished, iterator, result),
                        finished.errback)
                    break
                result = waiting



class UnCooperator(object):
    """
    An L{UnCooperator} looks like a L{twisted.internet.task.Cooperator} but it
    doesn't try to be cooperative.  It iterates over iterators as fast as it
    can.
    """
    def cooperate(self, iterator):
        """
        Create and start an uncooperative task for the given iterator.
        """
        return _MinimallyCooperativeTask(iterator)
