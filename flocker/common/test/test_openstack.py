# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for ``flocker.common.auto_openstack_logging``.
"""

from twisted.trial.unittest import SynchronousTestCase
from twisted.web.http import INTERNAL_SERVER_ERROR

from eliot.testing import LoggedMessage, assertContainsFields, capture_logging

from zope.interface import Interface, implementer

try:
    from novaclient.exceptions import ClientException as NovaClientException
    from keystoneclient.openstack.common.apiclient.exceptions import (
        HttpError as KeystoneHttpError,
    )
    from .. import auto_openstack_logging
    from .._openstack import NOVA_CLIENT_EXCEPTION, KEYSTONE_HTTP_ERROR
except ImportError as e:
    dependency_skip = str(e)

    def auto_openstack_logging(*a, **kw):
        return lambda cls: cls
else:
    dependency_skip = None

from requests import Response


class IDummy(Interface):
    def return_method():
        """
        Return something.
        """

    def raise_method():
        """
        Raise something.
        """


@implementer(IDummy)
class Dummy(object):
    def __init__(self, result):
        self._result = result

    def return_method(self):
        return self._result

    def raise_method(self):
        raise self._result


@auto_openstack_logging(IDummy, "_dummy")
class LoggingDummy(object):
    def __init__(self, dummy):
        self._dummy = dummy


class AutoOpenStackLoggingTests(SynchronousTestCase):
    """
    Tests for ``auto_openstack_logging``.
    """
    if dependency_skip is not None:
        skip = dependency_skip

    def test_return(self):
        """
        Decorated methods return the value returned by the original method.
        """
        result = object()
        logging_dummy = LoggingDummy(Dummy(result))
        self.assertIs(result, logging_dummy.return_method())

    def test_raise(self):
        """
        Decorated methods raise the same exception raised by the original
        method.
        """
        result = ValueError("Things.")
        logging_dummy = LoggingDummy(Dummy(result))
        exception = self.assertRaises(ValueError, logging_dummy.raise_method)
        self.assertIs(result, exception)

    @capture_logging(lambda self, logger: None)
    def test_novaclient_exception(self, logger):
        """
        The details of ``novaclient.exceptions.ClientException`` are logged
        when it is raised by the decorated method and the exception is still
        raised.
        """
        result = NovaClientException(
            code=INTERNAL_SERVER_ERROR,
            message="Some things went wrong with some other things.",
            details={"key": "value"},
            request_id="abcdefghijklmnopqrstuvwxyz",
            url="/foo/bar",
            method="POST",
        )
        logging_dummy = LoggingDummy(Dummy(result))
        self.assertRaises(NovaClientException, logging_dummy.raise_method)

        logged = LoggedMessage.of_type(
            logger.messages, NOVA_CLIENT_EXCEPTION,
        )[0]
        assertContainsFields(
            self, logged.message, {
                u"code": result.code,
                u"message": result.message,
                u"details": result.details,
                u"request_id": result.request_id,
                u"url": result.url,
                u"method": result.method,
            },
        )

    @capture_logging(lambda self, logger: None)
    def test_keystone_client_exception(self, logger):
        """
        ``keystoneclient.openstack.common.apiclient.exceptions.BadRequest`` is
        treated similarly to ``novaclient.exceptions.ClientException``.

        See ``test_novaclient_exception``.
        """
        response = Response()
        response._content = "hello world"
        result = KeystoneHttpError(
            message="Some things went wrong with some other things.",
            details={"key": "value"},
            response=response,
            request_id="abcdefghijklmnopqrstuvwxyz",
            url="/foo/bar",
            method="POST",
            http_status=INTERNAL_SERVER_ERROR,
        )
        logging_dummy = LoggingDummy(Dummy(result))
        self.assertRaises(KeystoneHttpError, logging_dummy.raise_method)

        logged = LoggedMessage.of_type(
            logger.messages, KEYSTONE_HTTP_ERROR,
        )[0]
        assertContainsFields(
            self, logged.message, {
                u"code": result.http_status,
                u"message": result.message,
                u"details": result.details,
                u"request_id": result.request_id,
                u"url": result.url,
                u"method": result.method,
                u"response": "hello world",
            },
        )
