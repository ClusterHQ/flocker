# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""Client implementation for talking to the geard daemon."""

import json

from zope.interface import Interface, implementer

from characteristic import attributes

from twisted.internet.defer import succeed, fail

from treq import request, content


GEAR_PORT = 43273


class AlreadyExists(Exception):
    """A unit with the given name already exists."""


class GearError(Exception):
    """Unexpected error received from gear daemon."""


@attributes(["name", "activation_state"])
class Unit(object):
    """Information about a unit managed by geard/systemd.

    :ivar unicode name: The name of the unit.

    :ivar unicode activation_state: The state of the unit in terms of
        systemd activation. Values indicate whether the unit is installed
        but not running (``u"inactive"``), starting (``u"activating"``),
        running (``u"active"``), failed (``u"failed"``) stopping
        (``u"deactivating"``) or stopped (either ``u"failed"`` or
        ``u"inactive"`` apparently).
    """


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

        This can be done multiple times in a row for the same unit.

        :param unicode unit_name: The name of the unit to stop.

        :return: ``Deferred`` that fires on success.
        """

    def list():
        """List all known units.

        :return: ``Deferred`` firing with ``set`` of :class:`Unit`.
        """


@implementer(IGearClient)
class GearClient(object):
    """Talk to the gear daemon over HTTP.

    :ivar bytes _base_url: Base URL for gear.
    """

    def __init__(self, hostname):
        """
        :param bytes hostname: Gear host to connect to.
        """
        self._base_url = b"http://%s:%d" % (hostname, GEAR_PORT)

    def _container_request(self, method, unit_name, operation=None, data=None):
        """Send HTTP request to gear.

        :param bytes method: The HTTP method to send, e.g. ``b"GET"``.

        :param unicode unit_name: The name of the unit.

        :param operation: ``None``, or extra ``unicode`` path element to add to
            the request URL path.

        :param data: ``None``, or object with a body for the request that
            can be serialized to JSON.

        :return: A ``Defered`` that fires with a response object.
        """
        path = b"/container/" + unit_name.encode("ascii")
        if operation is not None:
            path += b"/" + operation
        return self._request(method, path, data=data)

    def _request(self, method, path, data=None):
        """Send HTTP request to gear.

        :param bytes method: The HTTP method to send, e.g. ``b"GET"``.

        :param bytes path: Path to request.

        :param data: ``None``, or object with a body for the request that
            can be serialized to JSON.

        :return: A ``Defered`` that fires with a response object.
        """
        url = self._base_url + path
        if data is not None:
            data = json.dumps(data)
        return request(method, url, data=data, persistent=False)

    def _ensure_ok(self, response):
        """Make sure response indicates success.

        Also reads the body to ensure connection is closed.

        :param response: Response from treq request,
            ``twisted.web.iweb.IResponse`` provider.

        :return: ``Deferred`` that errbacks with ``GearError`` if the response
            is not successful (2xx HTTP response code).
        """
        d = content(response)
        # geard uses a variety of 2xx response codes. Filed treq issue
        # about having "is this a success?" API:
        # https://github.com/dreid/treq/issues/62
        if response.code // 100 != 2:
            d.addCallback(lambda data: fail(GearError(response.code, data)))
        return d

    def add(self, unit_name, image_name):
        checked = self.exists(unit_name)
        checked.addCallback(
            lambda exists: fail(AlreadyExists(unit_name)) if exists else None)
        checked.addCallback(
            lambda _: self._container_request(b"PUT", unit_name,
                                    data={u"Image": image_name,
                                          u"Started": True}))
        checked.addCallback(self._ensure_ok)
        return checked

    def exists(self, unit_name):
        d = self.list()
        def got_units(units):
            return unit_name in [unit.name for unit in units]
        d.addCallback(got_units)
        return d

    def remove(self, unit_name):
        d = self._container_request(b"PUT", unit_name, operation=b"stopped")
        d.addCallback(self._ensure_ok)
        d.addCallback(lambda _: self._container_request(b"DELETE", unit_name))
        d.addCallback(self._ensure_ok)
        return d

    def list(self):
        d = self._request(b"GET", b"/containers")
        d.addCallback(content)

        def got_body(data):
            values = json.loads(data)[u"Containers"]
            return set([Unit(name=unit[u"Id"],
                             activation_state=unit[u"ActiveState"])
                        for unit in values])
        d.addCallback(got_body)
        return d


@implementer(IGearClient)
class FakeGearClient(object):
    """In-memory fake that simulates talking to a gear daemon.

    The state the the simulated units is stored in memory.

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

    def list(self):
        result = set()
        for name in self._units:
            result.add(Unit(name=name, activation_state=u"active"))
        return succeed(result)
