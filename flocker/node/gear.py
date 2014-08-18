# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""Client implementation for talking to the geard daemon."""

import json

from zope.interface import Interface, implementer

from characteristic import attributes

from twisted.internet.defer import succeed, fail
from twisted.internet.task import deferLater
from twisted.internet import reactor

from treq import request, content

GEAR_PORT = 43273


class AlreadyExists(Exception):
    """A unit with the given name already exists."""


class GearError(Exception):
    """Unexpected error received from gear daemon."""


@attributes(["name", "activation_state", "sub_state", "container_image",
             "ports", "links"],
            defaults=dict(sub_state=None, container_image=None,
                          ports=(), links=()))
class Unit(object):
    """
    Information about a unit managed by geard/systemd.

    XXX: The container_image attribute defaults to `None` until we have a way
    to interrogate geard for the docker images associated with its
    containers. See https://github.com/ClusterHQ/flocker/issues/207

    :ivar unicode name: The name of the unit.

    :ivar unicode activation_state: The state of the unit in terms of
        systemd activation. Values indicate whether the unit is installed
        but not running (``u"inactive"``), starting (``u"activating"``),
        running (``u"active"``), failed (``u"failed"``) stopping
        (``u"deactivating"``) or stopped (either ``u"failed"`` or
        ``u"inactive"`` apparently). See
        https://github.com/ClusterHQ/flocker/issues/187 about using constants
        instead of strings.

    :ivar unicode sub_state: The systemd substate of the unit. Certain Unit
        types may have a number of additional substates, which are mapped to
        the five generalized activation states above. See
        http://www.freedesktop.org/software/systemd/man/systemd.html#Concepts

    :ivar unicode container_image: The docker image name associated with this
        gear unit

    :ivar list ports: The ``PortMap`` instances which define how connections to
        ports on the host are routed to ports exposed in the container.

    :ivar list links: The ``PortMap`` instances which define how connections to
        ports inside the container are routed to ports on the host.
    """


class IGearClient(Interface):
    """
    A client for the geard HTTP API.

    Note the difference in semantics between the results of ``add()``
    (firing does not indicate application started successfully)
    vs. ``remove()`` (firing indicates application has finished shutting
    down).
    """

    def add(unit_name, image_name, ports=None, links=None):
        """
        Install and start a new unit.

        Note that callers should not assume success indicates the unit has
        finished starting up. In addition to asynchronous nature of gear,
        even if container is up and running the application within it
        might still be starting up, e.g. it may not have bound the
        external ports yet. As a result the final success of application
        startup is out of scope for this method.

        :param unicode unit_name: The name of the unit to create.

        :param unicode image_name: The Docker image to use for the unit.

        :param list ports: A list of ``PortMap``\ s mapping ports exposed in
            the container to ports exposed on the host. Default ``None`` means
            that no port mappings will be configured for this unit.

        :param list links: A list of ``PortMap``\ s mapping ports forwarded
            from the container to ports on the host.

        :return: ``Deferred`` that fires on success, or errbacks with
            :class:`AlreadyExists` if a unit by that name already exists.
        """

    def exists(unit_name):
        """
        Check whether the unit exists.

        :param unicode unit_name: The name of the unit to create.

        :return: ``Deferred`` that fires with ``True`` if unit exists,
            otherwise ``False``.
        """

    def remove(unit_name):
        """
        Stop and delete the given unit.

        This can be done multiple times in a row for the same unit.

        :param unicode unit_name: The name of the unit to stop.

        :return: ``Deferred`` that fires once the unit has been stopped
            and removed.
        """

    def list():
        """
        List all known units.

        :return: ``Deferred`` firing with ``set`` of :class:`Unit`.
        """


@implementer(IGearClient)
class GearClient(object):
    """Talk to the gear daemon over HTTP.

    :ivar bytes _base_url: Base URL for gear.
    """

    def __init__(self, hostname):
        """
        :param unicode hostname: Gear host to connect to.
        """
        self._base_url = b"http://%s:%d" % (hostname.encode("ascii"),
                                            GEAR_PORT)

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

    def add(self, unit_name, image_name, ports=None, links=None):
        """
        See ``IGearClient.add`` for base documentation.

        Gear `NetworkLinks` are currently fixed to destination localhost. This
        allows us to control the actual target of the link using proxy / nat
        rules on the host machine without having to restart the gear unit.

        XXX: If gear allowed us to reconfigure links this wouldn't be
        necessary. See https://github.com/openshift/geard/issues/223

        XXX: As long as we need to set the target as 127.0.0.1 its also worth
        noting that gear will actually route the traffic to a non-loopback
        address on the host. So if your service or NAT rule on the host is
        configured for 127.0.0.1 only, it won't receive any traffic. See
        https://github.com/openshift/geard/issues/224
        """
        if ports is None:
            ports = []

        if links is None:
            links = []

        data = {
            u"Image": image_name, u"Started": True, u'Ports': [],
            u'NetworkLinks': []}

        for port in ports:
            data['Ports'].append(
                {u'Internal': port.internal_port,
                 u'External': port.external_port})

        for link in links:
            data['NetworkLinks'].append(
                {u'FromHost': u'127.0.0.1',
                 u'FromPort': link.internal_port,
                 u'ToHost': u'127.0.0.1',
                 u'ToPort': link.external_port}
            )

        checked = self.exists(unit_name)
        checked.addCallback(
            lambda exists: fail(AlreadyExists(unit_name)) if exists else None)
        checked.addCallback(
            lambda _: self._container_request(b"PUT", unit_name, data=data))
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

        def check_if_stopped(_=None):
            listing = self.list()

            def got_listing(units):
                matching_units = [unit for unit in units
                                  if unit.name == unit_name]
                if not matching_units:
                    return
                unit = matching_units[0]
                if unit.activation_state in (u"failed", u"inactive"):
                    return
                return deferLater(reactor, 0.1, check_if_stopped)
            listing.addCallback(got_listing)
            return listing
        d.addCallback(check_if_stopped)
        d.addCallback(lambda _: self._container_request(b"DELETE", unit_name))
        d.addCallback(self._ensure_ok)
        return d

    def list(self):
        d = self._request(b"GET", b"/containers?all=1")
        d.addCallback(content)

        def got_body(data):
            values = json.loads(data)[u"Containers"]
            # XXX: GearClient.list should also return container_image
            # information.
            # See https://github.com/ClusterHQ/flocker/issues/207
            # container_image=image_name,
            return set([Unit(name=unit[u"Id"],
                             activation_state=unit[u"ActiveState"],
                             sub_state=unit[u"SubState"],
                             container_image=None)
                        for unit in values])
        d.addCallback(got_body)
        return d


@implementer(IGearClient)
class FakeGearClient(object):
    """In-memory fake that simulates talking to a gear daemon.

    The state the the simulated units is stored in memory.

    :ivar dict _units: See ``units`` of ``__init__``\ .
    """

    def __init__(self, units=None):
        """
        :param dict units: A dictionary of canned ``Unit``\ s which will be
            manipulated and returned by the methods of this ``FakeGearClient``.
        :type units: ``dict`` mapping `unit_name` to ``Unit``\ .
        """
        if units is None:
            units = {}
        self._units = units

    def add(self, unit_name, image_name, ports=(), links=()):
        if unit_name in self._units:
            return fail(AlreadyExists(unit_name))
        self._units[unit_name] = Unit(
            name=unit_name,
            container_image=image_name,
            ports=ports,
            links=links,
            activation_state=u'active'
        )
        return succeed(None)

    def exists(self, unit_name):
        return succeed(unit_name in self._units)

    def remove(self, unit_name):
        if unit_name in self._units:
            del self._units[unit_name]
        return succeed(None)

    def list(self):
        # XXX: This is a hack so that functional and unit tests that use
        # GearClient.list can pass until the real GearClient.list can also
        # return container_image information, ports and links.
        # See https://github.com/ClusterHQ/flocker/issues/207
        incomplete_units = set()
        for unit in self._units.values():
            incomplete_units.add(
                Unit(name=unit.name,
                     ports=frozenset([1, 2]),
                     activation_state=unit.activation_state))
        return succeed(incomplete_units)


@attributes(['internal_port', 'external_port'])
class PortMap(object):
    """
    A record representing the mapping between a port exposed internally by a
    docker container and the corresponding external port on the host.

    :ivar int internal_port: The port number exposed by the container.
    :ivar int external_port: The port number exposed by the host.
    """
