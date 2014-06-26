# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""Client implementation for talking to the geard daemon."""

import json

from zope.interface import Interface, implementer

from twisted.web.http import NOT_FOUND
from twisted.internet.defer import succeed, fail
from twisted.internet.utils import getProcessValue

from treq import request, content

from characteristic import attributes

from ..common.docker import DockerClient
from ..testtools import loop_until

GEAR_PORT = 43273

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

        This can be done multiple times in a row for the same unit.

        :param unicode unit_name: The name of the unit to stop.

        :return: ``Deferred`` that fires on success.
        """

    def get(unit_name):
        """Return a record of the current state of the given unit.

        :param unicode unit_name: The name of the unit to get.

        :return: ``Deferred`` that fires on success with a ``GearUnit`` object.
        """


def systemd_unit_started(unit_name):
    d = getProcessValue(
        b'/usr/bin/systemctl', [b'is-active', b'ctr-%s' % (unit_name,)])
    def check_status(status):
        # XXX: Maybe we should also check the output here and fail if
        # the status is failed.
        return status == 0
    d.addCallback(check_status)
    return d


@implementer(IGearClient)
class GearClient(object):
    """Talk to the gear daemon over HTTP.

    :ivar bytes _base_url: Base URL for gear.
    """

    _docker = DockerClient()

    def __init__(self, hostname):
        """
        :param bytes hostname: Gear host to connect to.
        """
        self._base_url = b"http://%s:%d" % (hostname, GEAR_PORT)

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

    def add(self, unit_name, image_name, wait_for_start=False):
        checked = self.exists(unit_name)
        checked.addCallback(
            lambda exists: fail(AlreadyExists(unit_name)) if exists else None)
        checked.addCallback(
            lambda _: self._request(b"PUT", unit_name,
                                    data={u"Image": image_name,
                                          u"Started": True}))
        checked.addCallback(self._ensure_ok)
        if wait_for_start:
            checked.addCallback(
                loop_until, lambda: systemd_unit_started(unit_name))

        return checked

    def exists(self, unit_name):
        # status isn't really intended for this usage; better to use
        # listing (with option to list all) as part of
        # https://github.com/openshift/geard/issues/187
        d = self._request(b"GET", unit_name, operation=b"status")

        def got_response(response):
            result = content(response)
            # Gear can return a variety of 2xx success codes:
            if response.code // 100 == 2:
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

    def _filter_ids(self, unit_data):
        """
        """
        ids = []
        for record in unit_data["Containers"]:
            ids.append(record["Id"])
        return ids

    def _containers(self):
        d = request(b'GET', self._base_url + b'/containers', persistent=False)
        d.addCallback(content)
        d.addCallback(json.loads)
        d.addCallback(self._filter_ids)
        return d

    def _gear_unit_from_docker(self, unit_name):
        d = self._docker.inspect(unit_name)
        def gear_unit(inspect_data):
            record = inspect_data[0]
            image_name = record['Config']['Image']
            ports = []
            for port in record['Config']['ExposedPorts']:
                internal_port, internal_protocol = port.split('/', 1)
                internal_port = int(internal_port)
                for external_info  in record['HostConfig']['PortBindings'][port]:
                    host_port = int(external_info['HostPort'])
                    ports.append(PortMap(internal=internal_port, external=host_port))

            return GearUnit(
                unit_name=unit_name,
                image_name=image_name,
                ports=ports
            )
        d.addCallback(gear_unit)
        return d

    def get(self, unit_name):
        d = self.exists(unit_name)
        def check_exists(exists):
            if exists:
                return unit_name
            else:
                raise UnknownUnit(unit_name=unit_name)
        d.addCallback(check_exists)
        d.addCallback(self._gear_unit_from_docker)
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

        unit = GearUnit(unit_name=unit_name, image_name=image_name, ports=[])
        self._units[unit_name] = unit
        return succeed(None)

    def exists(self, unit_name):
        return succeed(unit_name in self._units)

    def remove(self, unit_name):
        if unit_name in self._units:
            del self._units[unit_name]
        return succeed(None)

    def get(self, unit_name):
        try:
            unit = self._units[unit_name]
        except KeyError:
            return fail(UnknownUnit(unit_name=unit_name))
        return succeed(unit)


@attributes(['internal', 'external'])
class PortMap(object):
    """
    A record representing the mapping between a port exposed internally by a
    docker container and the corresponding external port on the host.
    """


@attributes(['unit_name', 'image_name', 'ports'])
class GearUnit(object):
    """
    A record representing a single `geard` unit.
    """


@attributes(['unit_name'])
class UnknownUnit(Exception):
    pass
