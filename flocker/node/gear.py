# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""Client implementation for talking to the geard daemon."""

from zope.interface import Interface, implementer

from characteristic import attributes

from twisted.internet.defer import succeed, fail


class AlreadyExists(Exception):
    """A unit with the given name already exists."""


@attributes(["id", "variables"])
class GearEnvironment(object):
    """
    A collection of Geard unit environment variables associated with an
    environment ID.

    :ivar frozenset variables: A ``frozenset`` of tuples containing
        key and value pairs representing the environment variables.
    """

    def to_dict(self):
        """
        Convert to a dictionary suitable for serialising to JSON and then on to
        the Gear REST API.
        """
        variables = []
        for k, v in self.variables:
            variables.append(dict(name=k, value=v))
        return dict(id=self.id, variables=variables)


@attributes(["name", "activation_state", "sub_state", "container_image",
             "ports", "links", "environment"],
            defaults=dict(sub_state=None, container_image=None,
                          ports=(), links=(), environment=None))
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

    :ivar GearEnvironment environment: A ``GearEnvironment`` whose variables
        will be supplied to the gear unit or ``None`` if there are no
        environment variables for this unit.
    """


class IDockerClient(Interface):
    """
    A client for the Docker HTTP API.

    Currently somewhat geard-flavored, this will be fixed in followup
    issues.

    Note the difference in semantics between the results of ``add()``
    (firing does not indicate application started successfully)
    vs. ``remove()`` (firing indicates application has finished shutting
    down).
    """

    def add(unit_name, image_name, ports=None, links=None, environment=None):
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

        :param GearEnvironment environment: A ``GearEnvironment`` associating
            key value pairs with an environment ID. Default ``None`` means that
            no environment variables will be supplied to the unit.

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


@implementer(IDockerClient)
class FakeDockerClient(object):
    """In-memory fake that simulates talking to a docker daemon.

    The state the the simulated units is stored in memory.

    :ivar dict _units: See ``units`` of ``__init__``\ .
    """

    def __init__(self, units=None):
        """
        :param dict units: A dictionary of canned ``Unit``\ s which will be
        manipulated and returned by the methods of this
        ``FakeDockerClient``.
        :type units: ``dict`` mapping `unit_name` to ``Unit``\ .
        """
        if units is None:
            units = {}
        self._units = units

    def add(self, unit_name, image_name, ports=(), links=(), environment=None):
        if unit_name in self._units:
            return fail(AlreadyExists(unit_name))
        self._units[unit_name] = Unit(
            name=unit_name,
            container_image=image_name,
            ports=ports,
            links=links,
            environment=environment,
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
        # DockerClient.list can pass until the real DockerClient.list can also
        # return container_image information, ports and links.
        # See https://github.com/ClusterHQ/flocker/issues/207
        incomplete_units = set()
        for unit in self._units.values():
            incomplete_units.add(
                Unit(name=unit.name, activation_state=unit.activation_state))
        return succeed(incomplete_units)


@attributes(['internal_port', 'external_port'])
class PortMap(object):
    """
    A record representing the mapping between a port exposed internally by a
    docker container and the corresponding external port on the host.

    :ivar int internal_port: The port number exposed by the container.
    :ivar int external_port: The port number exposed by the host.
    """
