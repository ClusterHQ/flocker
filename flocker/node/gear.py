# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""Client implementation for talking to the geard daemon."""

import json

from zope.interface import Interface, implementer

from twisted.web.http import OK, NO_CONTENT, NOT_FOUND
from twisted.internet.defer import succeed, fail
from twisted.internet import reactor
from twisted.internet.task import deferLater

from treq import request, content


def workaround_geard_187():
    """Slight delay as workaround to
    https://github.com/openshift/geard/issues/187.

    :param value: Value to set as value of result ``Deferred``.

    :return: ``Deferred`` that fires after short delay.
    """
    return deferLater(reactor, 1, lambda: None)


class AlreadyExists(Exception):
    """A unit with the given name already exists."""


class GearError(Exception):
    """Unexpected error received from gear daemon."""


class IGearClient(Interface):
    """A client for the geard HTTP API."""

    def add(unit_name, image_name):
        """Install and start a new unit.

        :param unicode unit_name: The name of the unit to create.

        :param unicode image_name: The Docker image to use for the unit.

        :return: ``Deferred`` that fires on success, or errbacks with
            :class:`AlreadyExists` if a unit by that name already exists.
        """

    def exists(unit_name):
        """Check whether the unit exists.

        :param unicode unit_name: The name of the unit to create.

        :return: ``Deferred`` that fires with ``True`` if unit exists,
            otherwise ``False``.
        """

    def remove(unit_name):
        """Stop and delete the given unit.

        This can be done multiple times in the row for the same unit.

        :param unicode unit_name: The name of the unit to stop.

        :return: ``Deferred`` that fires on success.
        """


@implementer(IGearClient)
class GearClient(object):
    """Talk to the gear daemon over HTTP.

    :ivar Agent _agent: HTTP client used to talk to gear.
    :ivar bytes _base_url: Base URL for gear.
    """

    def __init__(self, hostname):
        """
        :param reactor: Reactor to use for HTTP connections.
        :param bytes hostname: Gear host to connect to.
        """
        self._base_url = b"http://%s:43273" % (hostname,)

    def _request(self, method, unit_name, operation=None, data=None):
        """Send HTTP request to gear.

        :param bytes method: The HTTP method to send, e.g. ``b"GET"``.

        :param unicode unit_name: The name of the unit.

        :param operation: ``None``, or extra ``unicode`` path element to add to
            the request URL path.

        :param data: ``None``, or object with a body for the request that
            can be serialized to JSON.

        :return: A ``Defered`` that fires with a response object.
        """
        url = self._base_url + b"/container/" + unit_name.encode("ascii")
        if operation is not None:
            url += b"/" + operation
        if data is not None:
            data = json.dumps(data)
        d = workaround_geard_187()
        d.addCallback(lambda _: request(method, url, data=data,
                                        persistent=False))
        return d

    def _ensure_ok(self, response):
        """Make sure response is OK.

        Also reads the body to ensure connection is closed.

        :param response: Response from treq request.

        :return: ``Deferred`` that errbacks with ``GearError`` if response
            is not OK.
        """
        d = content(response)
        if response.code not in (OK, NO_CONTENT):
            d.addCallback(lambda data: fail(GearError(response.code, data)))
        return d

    def add(self, unit_name, image_name):
        checked = self.exists(unit_name)
        checked.addCallback(
            lambda exists: fail(AlreadyExists(unit_name)) if exists else None)
        checked.addCallback(
            lambda _: self._request(b"PUT", unit_name,
                                     data={u"Image": image_name,
                                           u"Started": True}))
        checked.addCallback(self._ensure_ok)
        return checked


    def exists(self, unit_name):
        # status isn't really intended for this usage; better to use
        # listing (with option to list all) as part of
        # https://github.com/openshift/geard/issues/187
        d = self._request(b"GET", unit_name, operation=b"status")
        def got_response(response):
            result = content(response)
            if response.code in (OK, NO_CONTENT):
                result.addCallback(lambda _: True)
            elif response.code == NOT_FOUND:
                result.addCallback(lambda _: False)
            else:
                result.addCallback(
                    lambda data: fail(GearError(response.code, data)))
            return result
        d.addCallback(got_response)
        return d

    def remove(self, unit_name):
        d = self._request(b"PUT", unit_name, operation=b"stopped")
        d.addCallback(self._ensure_ok)
        d.addCallback(lambda _: self._request(b"DELETE", unit_name))
        d.addCallback(self._ensure_ok)
        return d


@implementer(IGearClient)
class FakeGearClient(object):
    """In-memory fake that simulates talking to a gear daemon.

    :ivar dict _units: Map ``unicode`` names of added units to dictionary
        containing information about them.
    """

    def __init__(self):
        self._units = {}

    def add(self, unit_name, image_name):
        if unit_name in self._units:
            return fail(AlreadyExists(unit_name))
        self._units[unit_name] = {}
        return succeed(None)

    def exists(self, unit_name):
        return succeed(unit_name in self._units)

    def remove(self, unit_name):
        if unit_name in self._units:
            del self._units[unit_name]
        return succeed(None)
