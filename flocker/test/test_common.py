# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for :py:mod:`flocker.common`.
"""

from twisted.python.failure import Failure
from twisted.internet.defer import CancelledError
from twisted.trial.unittest import TestCase

from ..common import EventChannel


class EventChannelTests(TestCase):
    """
    Tests for L{EventChannel}.
    """
    def test_callback(self):
        """
        L{EventChannel.callback} fires each L{Deferred} previously returned by
        L{EventChannel.subscribe}.
        """
        channel = EventChannel()
        d = channel.subscribe()
        channel.callback(3)
        return d.addCallback(self.assertEqual, 3)


    def test_errback(self):
        """
        L{EventChannel.errback} fires each L{Deferred} previously returned by
        L{EventChannel.subscribe}.
        """
        channel = EventChannel()
        d = channel.subscribe()
        channel.errback(Failure(ZeroDivisionError()))
        return self.assertFailure(d, ZeroDivisionError)


    def test_reentrant(self):
        """
        A callback on a L{Deferred} returned by
        L{EventChannel.subscribe} may use L{EventChannel.subscribe} to
        obtain a new L{Deferred} which is not fired with the same
        result as the first L{Deferred}.
        """
        waiting = []
        channel = EventChannel()
        d = channel.subscribe()
        d.addCallback(lambda ignored: waiting.append(channel.subscribe()))
        channel.callback(None)

        waiting[0].addBoth(waiting.append)
        # Prove it has no result yet
        self.assertEqual(1, len(waiting))


    def test_cancel(self):
        """
        A subscription L{Deferred} may be cancelled.
        """
        channel = EventChannel()
        d = channel.subscribe()
        d.cancel()
        return self.assertFailure(d, CancelledError)
