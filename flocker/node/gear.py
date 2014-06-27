# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""Client implementation for talking to the geard daemon."""

import json

from zope.interface import Interface, implementer

from twisted.web.http import NOT_FOUND
from twisted.internet.defer import succeed, fail

from treq import request, content

from characteristic import attributes

from ..volume.service import _docker_command

GEAR_PORT = 43273


class AlreadyExists(Exception):
    """A unit with the given name already exists."""


class GearError(Exception):
    """Unexpected error received from gear daemon."""


class IGearClient(Interface):
    """A client for the geard HTTP API."""

    def add(unit_name, image_name, ports=None):
        """Install and start a new unit.

        :param unicode unit_name: The name of the unit to create.

        :param unicode image_name: The Docker image to use for the unit.

        :param list ports: A list of ``PortMap``\ s mapping ports exposed in the
            container to ports exposed on the host.

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
        """Enumerate all geard units

        :return: A ``list`` of ``GearUnit``\ s
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

    def add(self, unit_name, image_name, ports=None):
        if ports is None:
            ports = []

        checked = self.exists(unit_name)
        data = {u"Image": image_name, u"Started": True, u'Ports': []}
        for port in ports:
            data['Ports'].append({u'Internal': port.internal, u'External': port.external})
        checked.addCallback(
            lambda exists: fail(AlreadyExists(unit_name)) if exists else None)
        checked.addCallback(
            lambda _: self._request(b"PUT", unit_name, data=data))
        checked.addCallback(self._ensure_ok)
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

    def _docker_inspect(self, unit_name):
        d = _docker_command(reactor, ['inspect', unit_name])
        d.addCallback(json.loads)
        return d

    def _gear_unit_from_docker(self, unit_name):
        d = workaround_geard_187()
        d.addCallback(lambda ignored: self._docker_inspect(unit_name))
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
        d = self._containers()
        def name_exists(unit_names):
            if unit_name in unit_names:
                return unit_name
            raise UnknownUnit(unit_name=unit_name)
        d.addCallback(name_exists)
        d.addCallback(self._gear_unit_from_docker)
        return d

@attributes(['unit_name'])
class UnknownUnit(Exception):
    pass

@implementer(IGearClient)
class FakeGearClient(object):
    """In-memory fake that simulates talking to a gear daemon.

    The state the the simulated units is stored in memory.

    :ivar dict _units: Map ``unicode`` names of added units to dictionary
        containing information about them.
    """

    def __init__(self):
        self._units = {}

    def add(self, unit_name, image_name, ports=None):
        if ports is None:
            ports = []

        if unit_name in self._units:
            return fail(AlreadyExists(unit_name))
        unit = GearUnit(
            unit_name=unit_name,
            image_name=image_name,
            ports=ports
        )
        self._units[unit_name] = unit
        return succeed(None)

    def exists(self, unit_name):
        return succeed(unit_name in self._units)

    def remove(self, unit_name):
        if unit_name in self._units:
            del self._units[unit_name]
        return succeed(None)

    def list(self):
        """
        """
        return self._units.values()


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
