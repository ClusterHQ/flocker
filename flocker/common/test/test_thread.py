# Copyright ClusterHQ Inc.  See LICENSE file for details.

# """
# Tests for ``flocker.common._thread``.
# """

from zope.interface import Interface, implementer

from twisted.trial.unittest import SynchronousTestCase, TestCase
from twisted.python.failure import Failure
from twisted.python.threadpool import ThreadPool

from pyrsistent import PRecord, field

from .. import auto_threaded


class IStub(Interface):
    def method(self, a, b, c):
        pass


@implementer(IStub)
class Spy(object):
    def __init__(self):
        self.calls = []

    def method(self, a, b, c):
        self.calls.append((a, b, c))
        return a + b + c


@auto_threaded(IStub, "reactor", "provider", "threadpool")
class AsyncSpy(PRecord):
    reactor = field()
    provider = field()
    threadpool = field()


class NonThreadPool(object):
    def callInThreadWithCallback(self, onResult, func, *args, **kw):
        try:
            result = func(*args, **kw)
        except:
            onResult(Failure())
        else:
            onResult(result)


class AutoThreadedTests(SynchronousTestCase):
    """
    Tests for ``flocker.common.auto_threaded``.
    """
    def setUp(self):
        self.reactor = object()
        self.threadpool = object()
        # Some unique objects that support ``+``
        self.a = [object()]
        self.b = [object()]
        self.c = [object()]
        self.spy = Spy()
        self.async_spy = AsyncSpy(
            reactor=self.reactor, threadpool=self.threadpool, provider=self.spy
        )

    def test_called_with_same_arguments(self):
        """
        A class can be decorated with ``auto_threaded`` with an interface and a
        provider of that interface.  When methods from the interface are called
        on instances of the class, the corresponding method is called with the
        same arguments on the provider of the interface.
        """
        self.async_spy.method(self.a, c=self.c, b=self.b)
        self.assertEqual([(self.a, self.b, self.c)], self.spy.calls)

    def test_success_result(self):
        """
        When methods from the interface are called on instances of the class, a
        ``Deferred`` is returned which fires with the result of the call to the
        corresponding method on the provider of the interface.
        """
        args = (self.a, self.b, self.c)
        result = self.successResultOf(self.async_spy.method(*args))
        self.assertEqual(self.spy.method(*args), result)

    def test_failure_result(self):
        """
        When the corresponding method on the provider of the interface raises
        an exception, the ``Deferred`` fires with a ``Failure`` representing
        that exception.
        """
        self.failureResultOf(
            self.async_spy.method(None, None, None),
            TypeError
        )

    def test_called_in_threadpool(self):
        """
        The corresponding method of the provider of the interface is called in
        a thread using the threadpool specified to ``auto_threaded``.
        """
        self.async_spy.method(self.a, self.b, self.c)


class AutoThreadedIntegrationTests(TestCase):
    """
    Tests for ``auto_threaded`` in combination with a real thread pool,
    ``twisted.python.threads.ThreadPool``.
    """
    def test_integration(self):
        """
        ``auto_threaded`` works with ``twisted.python.threads.ThreadPool``.
        """
        from twisted.internet import reactor

        threadpool = ThreadPool(minthreads=1, name=self.id())
        threadpool.start()
        self.addCleanup(threadpool.stop)

        spy = Spy()
        async_spy = AsyncSpy(
            reactor=reactor, threadpool=threadpool, provider=spy
        )

        a = [object()]
        b = [object()]
        c = [object()]
        result = async_spy.method(a, b, c)
        result.addCallback(self.assertEqual, spy.method(a, b, c))
        return result
