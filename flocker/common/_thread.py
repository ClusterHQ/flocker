# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Some thread-related tools.
"""

from twisted.internet.threads import deferToThreadPool

from ._interface import interface_decorator


def _threaded_method(method_name, sync_name, reactor_name, threadpool_name):
    """
    Create a method that calls another method in a threadpool.

    :param str method_name: The name of the method to look up on the "sync"
        object.
    :param str sync_name: The name of the attribute of ``self`` on which to
        look up the other method to run.  This is the "sync" object.
    :param str reactor_name: The name of the attribute of ``self`` referencing
        the reactor to use to get results back to the calling thread.
    :param str threadpool_name: The name of the attribute of ``self``
        referencing a ``twisted.python.threadpool.ThreadPool`` instance to use
        to run the method in a different thread.

    :return: The new thread-using method.  It has the same signature as the
             original method except it returns a ``Deferred`` that fires with
             the original method's result.
    """
    def _run_in_thread(self, *args, **kwargs):
        reactor = getattr(self, reactor_name)
        sync = getattr(self, sync_name)
        threadpool = getattr(self, threadpool_name)
        original = getattr(sync, method_name)
        return deferToThreadPool(
            reactor, threadpool, original, *args, **kwargs
        )
    return _run_in_thread


def auto_threaded(interface, reactor, sync, threadpool):
    """
    Create a class decorator which will add thread-based asynchronous versions
    of all of the methods on ``interface``.

    :param zope.interface.InterfaceClass interface: The interface from which to
        take methods.
    :param str reactor: The name of an attribute on instances of the decorated
        class.  The attribute should refer to the reactor which is running in
        the thread where the instance is being used (typically the single
        global reactor running in the main thread).
    :param str sync: The name of an attribute on instances of the decorated
        class.  The attribute should refer to a provider of ``interface``.
        That object will have its methods called in a threadpool to convert
        them from blocking to asynchronous.
    :param str threadpool: The name of an attribute on instances of the
        decorated class.  The attribute should refer to a
        ``twisted.python.threadpool.ThreadPool`` instance which will be used to
        call methods of the object named by ``sync``.

    :return: The class decorator.
    """
    return interface_decorator(
        "auto_threaded",
        interface, _threaded_method,
        sync, reactor, threadpool,
    )
