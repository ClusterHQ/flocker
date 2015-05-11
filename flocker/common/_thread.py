# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Some thread-related tools.
"""

from zope.interface.interface import Method

from twisted.internet.threads import deferToThreadPool


# TODO: Add tests and documentation for this, make it public (somewhere else).
# https://clusterhq.atlassian.net/browse/FLOC-1847
def _interface_decorator(decorator_name, interface, method_decorator,
                         *args, **kwargs):
    """
    Create a class decorator which applies a method decorator to each method of
    an interface.

    :param str decorator_name: A human-meaningful name for the class decorator
        that will be returned by this function.
    :param zope.interface.InterfaceClass interface: The interface from which to
        take methods.
    :param method_decorator: A callable which will decorate a method from the
        interface.  It will be called with the name of the method as the first
        argument and any additional positional and keyword arguments passed to
        ``_interface_decorator``.

    :return: The class decorator.
    """
    for method_name in interface.names():
        if not isinstance(interface[method_name], Method):
            raise TypeError(
                "{} does not support interfaces with non-methods "
                "attributes".format(decorator_name)
            )

    def _class_decorator(cls):
        for name in interface.names():
            setattr(cls, name, method_decorator(name, *args, **kwargs))
        return cls
    return _class_decorator


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
    return _interface_decorator(
        "auto_threaded",
        interface, _threaded_method,
        sync, reactor, threadpool,
    )


# TODO: After _interface_decorator is public, move this and
# auto_openstack_logging into (or at least nearer)
# flocker/node/agents/cinder.py
from eliot import Field, MessageType

CODE = Field.for_types("code", [int], u"The HTTP response code.")
MESSAGE = Field.for_types(
    "message", [bytes, unicode],
    u"A human-readable error message given by the response.",
)
DETAILS = Field.for_types("details", [dict], u"Extra details about the error.")
REQUEST_ID = Field.for_types(
    "request_id", [bytes, unicode],
    u"The unique identifier assigned by the server for this request.",
)
URL = Field.for_types("url", [bytes, unicode], u"The request URL.")
METHOD = Field.for_types("method", [bytes, unicode], u"The request method.")

NOVA_CLIENT_EXCEPTION = MessageType(
    u"openstack:nova_client_exception", [
        CODE,
        MESSAGE,
        DETAILS,
        REQUEST_ID,
        URL,
        METHOD,
    ],
)

RESPONSE = Field.for_types("response", [bytes, unicode], u"The response body.")

KEYSTONE_HTTP_ERROR = MessageType(
    u"openstack:keystone_http_error", [
        CODE,
        RESPONSE,
        MESSAGE,
        DETAILS,
        REQUEST_ID,
        URL,
        METHOD,
    ],
)

from novaclient.exceptions import ClientException as NovaClientException
from keystoneclient.openstack.common.apiclient.exceptions import (
    HttpError as KeystoneHttpError,
)


def _openstack_logged_method(method_name, original_name):
    """
    Run a method and log additional information about any exceptions that are
    raised.

    :param str method_name: The name of the method of the wrapped object to
        call.
    :param str original_name: The name of the attribute of self where the
        wrapped object can be found.

    :return: A function which will call the method of the wrapped object and do
        the extra exception logging.
    """
    def _run_with_logging(self, *args, **kwargs):
        original = getattr(self, original_name)
        method = getattr(original, method_name)
        try:
            return method(*args, **kwargs)
        except NovaClientException as e:
            NOVA_CLIENT_EXCEPTION(
                code=e.code,
                message=e.message,
                details=e.details,
                request_id=e.request_id,
                url=e.url,
                method=e.method,
            ).write()
            raise
        except KeystoneHttpError as e:
            KEYSTONE_HTTP_ERROR(
                code=e.http_status,
                message=e.message,
                details=e.details,
                request_id=e.request_id,
                url=e.url,
                method=e.method,
                response=e.response.text,
            ).write()
            raise
    return _run_with_logging


def auto_openstack_logging(interface, original):
    """
    Create a class decorator which will add OpenStack-specific exception
    logging versions versions of all of the methods on ``interface``.
    Specifically, some Nova and Cinder client exceptions will have all of their
    details logged any time they are raised.

    :param zope.interface.InterfaceClass interface: The interface from which to
        take methods.
    :param str original: The name of an attribute on instances of the decorated
        class.  The attribute should refer to a provider of ``interface``.
        That object will have all of its methods called with additional
        exception logging to make more details of the underlying OpenStack API
        calls available.

    :return: The class decorator.
    """
    return _interface_decorator(
        "auto_openstack_logging",
        interface,
        _openstack_logged_method,
        original,
    )
