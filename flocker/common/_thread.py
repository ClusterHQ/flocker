# FLOC-1549

# from twisted.internet.threads import deferToThreadPool


# def _threaded_method(method_name, reactor_name, sync_name, threadpool_name):
#     def _run_in_thread(self, *args, **kwargs):
#         reactor = getattr(self, reactor_name)
#         sync = getattr(self, sync_name)
#         threadpool = getattr(self, threadpool_name)
#         original = getattr(sync, method_name)
#         return deferToThreadPool(reactor, threadpool, original, *args, **kwargs)
#     return _run_in_thread


# def auto_threaded(interface, sync, threadpool):
#     def _threaded_class_decorator(cls):
#         for name in interface.names():
#             cls.__dict__[name] = _threaded_method(
#                 name, sync, threadpool)
#             )
#         return cls
#     return _threaded_class_decorator

