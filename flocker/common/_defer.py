# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
# -*- test-case-name: flocker.node.test.test_deploy -*-

"""
Various helpers for dealing with Deferred APIs in flocker.
"""

from twisted.internet.defer import Deferred, gatherResults
from twisted.python import log


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
