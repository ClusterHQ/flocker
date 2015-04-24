# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for ``flocker.common._thread``.
"""

from zope.interface import Attribute, Interface, implementer

from twisted.trial.unittest import SynchronousTestCase, TestCase
from twisted.python.failure import Failure
from twisted.python.threadpool import ThreadPool

from pyrsistent import PRecord, field

from .. import auto_threaded


class IStub(Interface):
    """
    An interface that can be passed to ``auto_threaded``.
    """
    def method(a, b, c):
        pass


@implementer(IStub)
class Spy(object):
    """
    A synchronous implementation of ``IStub`` that will be wrapped by an
    ``auto-threaded``-decorated class.  It also records calls to make some
    tests easier.

    :ivar list calls: A list of tuples of the arguments passed to ``method``.
    """
    def __init__(self):
        self.calls = []

    def method(self, a, b, c):
        """
        Record this method call and return the concatenation of all the
        arguments.
        """
        self.calls.append((a, b, c))
        return a + b + c


@auto_threaded(IStub, "reactor", "provider", "threadpool")
class AsyncSpy(PRecord):
    """
    An automatically asynchronous version of ``Spy``.
    """
    reactor = field()
    provider = field()
    threadpool = field()


class NonThreadPool(object):
    """
    A stand-in for ``twisted.python.threadpool.ThreadPool`` so that the
    majority of the test suite does not need to use multithreading.

    This implementation takes the function call which is meant to run in a
    thread pool and runs it synchronously in the calling thread.

    :ivar int calls: The number of calls which have been dispatched to this
        object.
    """
    calls = 0

    def callInThreadWithCallback(self, onResult, func, *args, **kw):
        self.calls += 1
        try:
            result = func(*args, **kw)
        except:
            onResult(False, Failure())
        else:
            onResult(True, result)


class NonReactor(object):
    """
    A stand-in for ``twisted.internet.reactor`` which fits into the execution
    model defined by ``NonThreadPool``.
    """
    def callFromThread(self, f, *args, **kwargs):
        f(*args, **kwargs)


class AutoThreadedTests(SynchronousTestCase):
    """
    Tests for ``flocker.common.auto_threaded``.
    """
    def setUp(self):
        self.reactor = NonReactor()
        self.threadpool = NonThreadPool()
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
        before = self.threadpool.calls
        self.successResultOf(self.async_spy.method(self.a, self.b, self.c))
        after = self.threadpool.calls
        self.assertEqual((before, after), (0, 1))

    def test_attributes_rejected(self):
        """
        Interfaces that use ``Attribute`` are not supported.
        """
        class IAttributeHaving(Interface):
            def some_method():
                pass

            x = Attribute("some attribute")

        self.assertRaises(
            TypeError,
            auto_threaded,
            IAttributeHaving, "reactor", "sync", "threadpool"
        )


class AutoThreadedIntegrationTests(TestCase):
    """
    Tests for ``auto_threaded`` in combination with a real reactor and a real
    thread pool, ``twisted.python.threads.ThreadPool``.
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
