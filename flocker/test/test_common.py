# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for :py:mod:`flocker.common`.
"""

from twisted.python.failure import Failure
from twisted.internet.defer import CancelledError, Deferred, succeed, fail
from twisted.trial.unittest import TestCase

from .common import ArbitraryException
from ..common import EventChannel, UnCooperator


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



class UnCooperatorTests(TestCase):
    """
    Tests for L{UnCooperator}.
    """
    def setUp(self):
        self.cooperator = UnCooperator()
        self.cooperate = lambda seq: self.cooperator.cooperate(iter(seq))


    def test_empty(self):
        """
        The task returned by L{UnCooperator.cooperate} when called with an
        empty iterator is already done.
        """
        cooperating = self.cooperate([]).whenDone()
        self.assertIs(None, self.successResultOf(cooperating))


    def test_alreadySucceededElements(self):
        """
        The task returned by L{UnCooperator.cooperate} when called with an
        iterator of L{Deferred} instances that already have results is already
        done.
        """
        cooperating = self.cooperate([succeed(None)]).whenDone()
        self.assertIs(None, self.successResultOf(cooperating))


    def test_nonDeferredElements(self):
        """
        The task returned by L{UnCooperator.cooperate} when called with an
        iterator of objects that are not L{Deferred} instances is already done.
        """
        cooperating = self.cooperate([None]).whenDone()
        self.assertIs(None, self.successResultOf(cooperating))


    def test_resultIsLastValue(self):
        """
        The result of the L{Deferred} returned by the C{whenDone} method of the
        task returned by L{UnCooperator.cooperate} is the value of the last
        element of the iterator.
        """
        result = object()
        cooperating = self.cooperate([None, result]).whenDone()
        self.assertIs(result, self.successResultOf(cooperating))


    def test_waitForDeferreds(self):
        """
        When the iterator passed to L{UnCooperator.cooperate} includes a
        L{Deferred} instance that does not yet have a result, the task returned
        also does not have a result.
        """
        cooperating = self.cooperate([Deferred()]).whenDone()
        self.assertNoResult(cooperating)


    def test_doneWhenElementDeferredDone(self):
        """
        When the not yet complete L{Deferred} in the iterator passed to
        L{UnCooperator.cooperate} does complete, the task returned completes.
        """
        result = object()
        waiting = Deferred()
        cooperating = self.cooperate([waiting]).whenDone()
        waiting.callback(result)
        self.assertIs(result, self.successResultOf(cooperating))


    def test_errorOnException(self):
        """
        When an exception (except StopIteration) is raised trying to get the
        next element of the iterator the L{Deferred} returned by the
        C{whenDone} method of the task returned by L{UnCooperator.cooperate}
        fires with a L{Failure}.
        """
        def broken():
            raise ArbitraryException()
            yield

        cooperating = self.cooperate(broken()).whenDone()
        self.failureResultOf(cooperating, ArbitraryException)


    def test_errorOnFailure(self):
        """
        Like L{test_errorOnException} but for the case where an element of the
        iterator is a L{Deferred} that fires with a L{Failure}.
        """
        def broken():
            yield fail(ArbitraryException())

        cooperating = self.cooperate(broken()).whenDone()
        self.failureResultOf(cooperating, ArbitraryException)
