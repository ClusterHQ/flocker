# FLOC-1549

from twisted.internet.threads import deferToThreadPool


def _threaded_method(method_name, reactor_name, sync_name, threadpool_name):
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
    def _threaded_class_decorator(cls):
        for name in interface.names():
            setattr(
                cls, name, _threaded_method(name, reactor, sync, threadpool)
            )
        return cls
    return _threaded_class_decorator

