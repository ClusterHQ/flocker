# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
OpenStack-related tools.
"""

# After _interface_decorator is public, move this and auto_openstack_logging
# into (or at least nearer) flocker/node/agents/cinder.py.
from eliot import Field, MessageType, Message

from novaclient.exceptions import ClientException as NovaClientException
from keystoneclient.openstack.common.apiclient.exceptions import (
    HttpError as KeystoneHttpError,
)

from ._thread import _interface_decorator


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
        Message.new(
            method=method.__name__, args=args, kwargs=kwargs
        ).write()
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
