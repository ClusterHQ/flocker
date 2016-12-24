# Copyright ClusterHQ Inc.  See LICENSE file for details.
# -*- test-case-name: flocker.node.test.test_docker -*-

"""
Docker API client.
"""

from __future__ import absolute_import

from errno import ECONNREFUSED
from socket import error as socket_error
from functools import partial

from docker import Client
from docker.errors import APIError

from requests.exceptions import ConnectionError
from requests.packages.urllib3.exceptions import ProtocolError

from twisted.web.http import INTERNAL_SERVER_ERROR

from ..common import (
    retry_if, decorate_methods, with_retry, get_default_retry_steps,
)


class TimeoutClient(Client):
    """
    A subclass of docker.Client that sets any infinite timeouts to the
    provided ``long_timeout`` value.

    This class is a temporary fix until docker-py is released with
    PR #625 or similar. See https://github.com/docker/docker-py/pull/625

    See Flocker JIRA Issue FLOC-2082
    """

    def __init__(self, *args, **kw):
        """
        :param timedelta long_timeout: A timeout to use for any request that
            doesn't have any other timeout specified.
        """
        self._long_timeout = kw.pop('long_timeout', None)
        Client.__init__(self, *args, **kw)

    def _set_request_timeout(self, kwargs):
        """
        Prepare the kwargs for an HTTP request by inserting the timeout
        parameter, if not already present.  If the timeout is infinite,
        set it to the ``long_timeout`` parameter.
        """
        kwargs = Client._set_request_timeout(self, kwargs)
        if kwargs['timeout'] is None and self._long_timeout is not None:
            kwargs['timeout'] = self._long_timeout.total_seconds()
        return kwargs


def _is_known_retryable(exception):
    """
    Determine if the text of a Docker 500 error represents a case which
    warrants an automatic retry.

    :param Exception exception: The exception from a ``docker.Client`` method
        call.

    :return bool: ``True`` if the exception represents a failure that is likely
        transient and a retry makes sense, ``False`` otherwise.
    """
    # A problem coming out of Docker itself
    if isinstance(exception, APIError):
        if exception.response.status_code == INTERNAL_SERVER_ERROR:
            error_text = exception.response.text
            return any(
                known in error_text
                for known
                in [
                    # https://github.com/docker/docker/issues/18194
                    u"Unknown device",
                    # https://github.com/docker/docker/issues/17653
                    u"no such device",
                ]
            )

    # A connection problem coming from the requests library used by docker-py
    if isinstance(exception, ConnectionError):
        if (
            len(exception.args) > 0 and
            isinstance(exception.args[0], ProtocolError)
        ):
            if (
                len(exception.args[0].args) > 1 and
                isinstance(exception.args[0].args[1], socket_error)
            ):
                return exception.args[0].args[1].errno in {ECONNREFUSED}

    return False


def dockerpy_client(**kwargs):
    """
    Create a ``docker.Client`` configured to be more reliable than the default.

    The client will impose additional timeouts on certain operations that
    ``docker.Client`` does not impose timeouts on.  It will also retry
    operations that fail in ways that retrying is known to help fix.
    """
    if "version" not in kwargs:
        kwargs = kwargs.copy()
        kwargs["version"] = "1.15"
    return decorate_methods(
        TimeoutClient(**kwargs),
        partial(
            with_retry,
            should_retry=retry_if(_is_known_retryable),
            steps=get_default_retry_steps(),
        ),
    )
