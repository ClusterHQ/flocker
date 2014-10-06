# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Docker API client.
"""

from __future__ import absolute_import

from time import sleep

from zope.interface import Interface, implementer

from docker import Client
from docker.errors import APIError

from characteristic import attributes, Attribute

from twisted.python.components import proxyForInterface
from twisted.internet.defer import succeed, fail
from twisted.internet.threads import deferToThread
from twisted.web.http import NOT_FOUND, INTERNAL_SERVER_ERROR


class AlreadyExists(Exception):
    """A unit with the given name already exists."""


@attributes(["variables"])
class Environment(object):
    """
    A collection of environment variables.

    :ivar frozenset variables: A ``frozenset`` of tuples containing
        key and value pairs representing the environment variables.
    """
    def to_dict(self):
        """
        Convert to a dictionary suitable for serialising to JSON and then on to
        the Docker API.

        :return: ``dict`` mapping keys to values.
        """
        return dict(self.variables)


@attributes(["node_path", "container_path"])
class Volume(object):
    """
    A Docker volume.

    :ivar FilePath node_path: The volume's path on the node's
    filesystem.

    :ivar FilePath container_path: The volume's path within the
    container.
    """


@attributes(["name", "container_name", "activation_state",
             Attribute("container_image", default_value=None),
             Attribute("ports", default_value=()),
             Attribute("environment", default_value=None),
             Attribute("volumes", default_value=())])
class Unit(object):
    """
    Information about a unit managed by Docker.

    XXX "Unit" is geard terminology, and should be renamed. See
    https://github.com/ClusterHQ/flocker/issues/819

    :ivar unicode name: The name of the unit, which may not be the same as
        the container name.

    :ivar unicode container_name: The name of the container where the
        application is running.

    :ivar unicode activation_state: The state of the
        container. ``u"active"`` indicates it is running, ``u"inactive"``
        indicates it is not running. See
        https://github.com/ClusterHQ/flocker/issues/187 about using
        constants instead of strings and other improvements.

    :ivar unicode container_image: The docker image name associated with this
        container.

    :ivar tuple ports: The ``PortMap`` instances which define how
        connections to ports on the host are routed to ports exposed in
        the container.

    :ivar Environment environment: An ``Environment`` whose variables
        will be supplied to the Docker container or ``None`` if there are no
        environment variables for this container.

    :ivar volumes: A ``tuple`` of ``Volume`` instances, the container's
        volumes.
    """


class IDockerClient(Interface):
    """
    A client for the Docker HTTP API.

    Note the difference in semantics between the results of ``add()``
    (firing does not indicate application started successfully)
    vs. ``remove()`` (firing indicates application has finished shutting
    down).
    """

    def add(unit_name, image_name, ports=None, environment=None, volumes=()):
        """
        Install and start a new unit.

        Note that callers should not assume success indicates the unit has
        finished starting up. In addition to asynchronous nature of Docker,
        even if container is up and running the application within it
        might still be starting up, e.g. it may not have bound the
        external ports yet. As a result the final success of application
        startup is out of scope for this method.

        :param unicode unit_name: The name of the unit to create.

        :param unicode image_name: The Docker image to use for the unit.

        :param list ports: A list of ``PortMap``\ s mapping ports exposed in
            the container to ports exposed on the host. Default ``None`` means
            that no port mappings will be configured for this unit.

        :param Environment environment: Environment variables for the
            container. Default ``None`` means that no environment
            variables will be supplied to the unit.

        :param volumes: A sequence of ``Volume`` instances to mount.

        :return: ``Deferred`` that fires on success, or errbacks with
            :class:`AlreadyExists` if a unit by that name already exists.
        """

    def exists(unit_name):
        """
        Check whether the unit exists.

        :param unicode unit_name: The name of the unit whose existence
            we're checking.

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

    def add(self, unit_name, image_name, ports=(), environment=None,
            volumes=()):
        if unit_name in self._units:
            return fail(AlreadyExists(unit_name))
        self._units[unit_name] = Unit(
            name=unit_name,
            container_name=unit_name,
            container_image=image_name,
            ports=ports,
            environment=environment,
            volumes=volumes,
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
        # return volumes information.
        # See https://github.com/ClusterHQ/flocker/issues/289
        incomplete_units = set()
        for unit in self._units.values():
            incomplete_units.add(
                Unit(name=unit.name, container_name=unit.name,
                     activation_state=unit.activation_state,
                     container_image=unit.container_image,
                     ports=tuple(unit.ports)))
        return succeed(incomplete_units)


@attributes(['internal_port', 'external_port'])
class PortMap(object):
    """
    A record representing the mapping between a port exposed internally by a
    docker container and the corresponding external port on the host.

    :ivar int internal_port: The port number exposed by the container.
    :ivar int external_port: The port number exposed by the host.
    """


# Basic namespace for Flocker containers:
BASE_NAMESPACE = u"flocker--"


@implementer(IDockerClient)
class DockerClient(object):
    """
    Talk to the real Docker server directly.

    Some operations can take a while (e.g. stopping a container), so we
    use a thread pool. See https://github.com/ClusterHQ/flocker/issues/718
    for using a custom thread pool.

    :ivar unicode namespace: A namespace prefix to add to container names
        so we don't clobber other applications interacting with Docker.
    """
    def __init__(self, namespace=BASE_NAMESPACE):
        self.namespace = namespace
        self._client = Client(version="1.12")

    def _to_container_name(self, unit_name):
        """
        Add the namespace to the container name.

        :param unicode unit_name: The unit's name.

        :return unicode: The container's name.
        """
        return self.namespace + unit_name

    def add(self, unit_name, image_name, ports=None, environment=None,
            volumes=()):
        container_name = self._to_container_name(unit_name)

        if environment is not None:
            environment = environment.to_dict()
        if ports is None:
            ports = []

        def _create():
            self._client.create_container(
                image_name,
                name=container_name,
                environment=environment,
                volumes=list(volume.container_path.path for volume in volumes),
                ports=[p.internal_port for p in ports])

        def _add():
            try:
                _create()
            except APIError as e:
                if e.response.status_code == NOT_FOUND:
                    # Image was not found, so we need to pull it first:
                    self._client.pull(image_name)
                    _create()
                else:
                    raise
            # Just because we got a response doesn't mean Docker has
            # actually updated any internal state yet! So if e.g. we did a
            # stop on this container Docker might well complain it knows
            # not the container of which we speak. To prevent this we poll
            # until it does exist.
            while not self._blocking_exists(container_name):
                sleep(0.001)
                continue
            self._client.start(container_name,
                               binds={volume.node_path.path:
                                      {u"bind": volume.container_path.path,
                                       u"ro": False}
                                      for volume in volumes},
                               port_bindings={p.internal_port: p.external_port
                                              for p in ports})
        d = deferToThread(_add)

        def _extract_error(failure):
            failure.trap(APIError)
            code = failure.value.response.status_code
            if code == 409:
                raise AlreadyExists(unit_name)
            return failure
        d.addErrback(_extract_error)
        return d

    def _blocking_exists(self, container_name):
        """
        Blocking API to check if container exists.

        :param unicode container_name: The name of the container whose
            existence we're checking.

        :return: ``True`` if unit exists, otherwise ``False``.
        """
        try:
            self._client.inspect_container(container_name)
            return True
        except APIError:
            return False

    def exists(self, unit_name):
        container_name = self._to_container_name(unit_name)
        return deferToThread(self._blocking_exists, container_name)

    def remove(self, unit_name):
        container_name = self._to_container_name(unit_name)

        def _remove():
            try:
                self._client.stop(container_name)
                self._client.remove_container(container_name)
            except APIError as e:
                # 500 error code is used for "this was already stopped" in
                # older versions of Docker. Newer versions of Docker API
                # give NOT_MODIFIED instead, so we can fix this when we
                # upgrade: https://github.com/ClusterHQ/flocker/issues/721
                if e.response.status_code in (
                        NOT_FOUND, INTERNAL_SERVER_ERROR):
                    return
                # Can't figure out how to get test coverage for this, but
                # it's definitely necessary:
                raise
        d = deferToThread(_remove)
        return d

    def list(self):
        def _list():
            result = set()
            ids = [d[u"Id"] for d in
                   self._client.containers(quiet=True, all=True)]
            for i in ids:
                data = self._client.inspect_container(i)
                state = (u"active" if data[u"State"][u"Running"]
                         else u"inactive")
                name = data[u"Name"]
                image = data[u"Config"][u"Image"]
                ports = []
                container_ports = data[u"NetworkSettings"][u"Ports"]
                if container_ports:
                    for internal, hostmap in container_ports.items():
                        internal_map = internal.split(u'/')
                        internal_port = internal_map[0]
                        internal_port = int(internal_port)
                        if hostmap:
                            for host in hostmap:
                                external_port = host[u"HostPort"]
                                external_port = int(external_port)
                                portmap = PortMap(internal_port=internal_port,
                                                  external_port=external_port)
                                ports.append(portmap)
                if name.startswith(u"/" + self.namespace):
                    name = name[1 + len(self.namespace):]
                else:
                    continue
                # XXX to extract volume info from the inspect results:
                # https://github.com/ClusterHQ/flocker/issues/289
                result.add(Unit(name=name,
                                container_name=self._to_container_name(name),
                                activation_state=state,
                                container_image=image,
                                ports=tuple(ports)))
            return result
        return deferToThread(_list)


class NamespacedDockerClient(proxyForInterface(IDockerClient, "_client")):
    """
    A Docker client that only shows and creates containers in a given
    namespace.

    Unlike ``DockerClient``, whose namespace is there to prevent conflicts
    with other Docker users, this class deals with Flocker's internal
    concept of namespaces. I.e. if hypothetically Docker container names
    supported path-based namespaces then ``DockerClient`` would look at
    containers in ``/flocker/`` and this class would look at containers in
    in ``/flocker/<namespace>/``.
    """
    def __init__(self, namespace):
        """
        :param unicode namespace: Namespace to restrict containers to.
        """
        self._client = DockerClient(
            namespace=BASE_NAMESPACE + namespace + u"--")
