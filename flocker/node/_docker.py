# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
# -*- test-case-name: flocker.node.test.test_docker -*-

"""
Docker API client.
"""

from __future__ import absolute_import

from time import sleep

from zope.interface import Interface, implementer

from docker import Client
from docker.errors import APIError
from docker.utils import create_host_config

from characteristic import attributes, Attribute

from twisted.python.components import proxyForInterface
from twisted.python.filepath import FilePath
from twisted.internet.defer import succeed, fail
from twisted.internet.threads import deferToThread
from twisted.web.http import NOT_FOUND, INTERNAL_SERVER_ERROR

from ..control._model import RestartNever, RestartAlways, RestartOnFailure


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
             Attribute("volumes", default_value=()),
             Attribute("mem_limit", default_value=None),
             Attribute("cpu_shares", default_value=None),
             Attribute("restart_policy", default_value=RestartNever()),
             ])
class Unit(object):
    """
    Information about a unit managed by Docker.

    XXX "Unit" is geard terminology, and should be renamed. See
    https://clusterhq.atlassian.net/browse/FLOC-819

    :ivar unicode name: The name of the unit, which may not be the same as
        the container name.

    :ivar unicode container_name: The name of the container where the
        application is running.

    :ivar unicode activation_state: The state of the
        container. ``u"active"`` indicates it is running, ``u"inactive"``
        indicates it is not running. See
        https://clusterhq.atlassian.net/browse/FLOC-187 about using
        constants instead of strings and other improvements.

    :ivar unicode container_image: The docker image name associated with this
        container.

    :ivar frozenset ports: The ``PortMap`` instances which define how
        connections to ports on the host are routed to ports exposed in
        the container.

    :ivar Environment environment: An ``Environment`` whose variables
        will be supplied to the Docker container or ``None`` if there are no
        environment variables for this container.

    :ivar volumes: A ``frozenset`` of ``Volume`` instances, the container's
        volumes.

    :ivar int mem_limit: The number of bytes to which to limit the in-core
        memory allocations of this unit.  Or ``None`` to apply no limits.  The
        behavior when the limit is encountered depends on the container
        execution driver but the likely behavior is for the container process
        to be killed (and therefore the container to exit).  Docker most likely
        maps this value onto the cgroups ``memory.limit_in_bytes`` value.

    :ivar int cpu_shares: The number of CPU shares to allocate to this unit.
        Or ``None`` to let it have the default number of shares.  Docker maps
        this value onto the cgroups ``cpu.shares`` value (the default of which
        is probably 1024).

    :ivar IRestartPolicy restart_policy: The restart policy of the container.
    """


class IDockerClient(Interface):
    """
    A client for the Docker HTTP API.

    Note the difference in semantics between the results of ``add()``
    (firing does not indicate application started successfully)
    vs. ``remove()`` (firing indicates application has finished shutting
    down).
    """

    def add(unit_name, image_name, ports=None, environment=None, volumes=(),
            mem_limit=None, cpu_shares=None, restart_policy=RestartNever()):
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

        :param int mem_limit: The number of bytes to which to limit the in-core
            memory allocations of the new unit.  Or ``None`` to apply no
            limits.

        :param int cpu_shares: The number of CPU shares to allocate to the new
            unit.  Or ``None`` to let it have the default number of shares.
            Docker maps this value onto the cgroups ``cpu.shares`` value (the
            default of which is probably 1024).

        :param IRestartPolicy restart_policy: The restart policy of the
            container.

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

    def add(self, unit_name, image_name, ports=frozenset(), environment=None,
            volumes=frozenset(), mem_limit=None, cpu_shares=None,
            restart_policy=RestartNever()):
        if unit_name in self._units:
            return fail(AlreadyExists(unit_name))
        self._units[unit_name] = Unit(
            name=unit_name,
            container_name=unit_name,
            container_image=image_name,
            ports=frozenset(ports),
            environment=environment,
            volumes=frozenset(volumes),
            activation_state=u'active',
            mem_limit=mem_limit,
            cpu_shares=cpu_shares,
            restart_policy=restart_policy,
        )
        return succeed(None)

    def exists(self, unit_name):
        return succeed(unit_name in self._units)

    def remove(self, unit_name):
        if unit_name in self._units:
            del self._units[unit_name]
        return succeed(None)

    def list(self):
        units = set(self._units.values())
        return succeed(units)


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
BASE_DOCKER_API_URL = u'unix://var/run/docker.sock'


@implementer(IDockerClient)
class DockerClient(object):
    """
    Talk to the real Docker server directly.

    Some operations can take a while (e.g. stopping a container), so we
    use a thread pool. See https://clusterhq.atlassian.net/browse/FLOC-718
    for using a custom thread pool.

    :ivar unicode namespace: A namespace prefix to add to container names
        so we don't clobber other applications interacting with Docker.
    """
    def __init__(self, namespace=BASE_NAMESPACE,
                 base_url=BASE_DOCKER_API_URL):
        self.namespace = namespace
        self._client = Client(version="1.15", base_url=base_url)

    def _to_container_name(self, unit_name):
        """
        Add the namespace to the container name.

        :param unicode unit_name: The unit's name.

        :return unicode: The container's name.
        """
        return self.namespace + unit_name

    def _parse_container_ports(self, data):
        """
        Parse the ports from a data structure representing the Ports
        configuration of a Docker container in the format returned by
        ``self._client.inspect_container`` and return a list containing
        ``PortMap`` instances mapped to the container and host exposed ports.

        :param dict data: The data structure for the representation of
            container and host port mappings in a single container.
            This takes the form of the ``NetworkSettings.Ports`` portion
            of a container's state and configuration as returned by inspecting
            the container. This is a dictionary mapping container ports to a
            list of host bindings, e.g.
            "3306/tcp": [{"HostIp": "0.0.0.0","HostPort": "53306"},
                         {"HostIp": "0.0.0.0","HostPort": "53307"}]

        :return list: A list that is either empty or contains ``PortMap``
            instances.
        """
        ports = []
        for internal, hostmap in data.items():
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
        return ports

    def _parse_restart_policy(self, data):
        """
        Parse the restart policy from the configuration of a Docker container
        in the format returned by ``self._client.inspect_container`` and return
        an ``IRestartPolicy``.

        :param dict data: The data structure representing the restart policy of
            a container, e.g.

            {"Name": "policy-name", "MaximumRetryCount": 0}

        :return IRestartPolicy: The model of the restart policy.

        :raises ValueError: if an unknown policy is passed.
        """
        POLICIES = {
            u"": lambda data:
                RestartNever(),
            u"always": lambda data:
                RestartAlways(),
            u"on-failure": lambda data:
                RestartOnFailure(
                    maximum_retry_count=data[u"MaximumRetryCount"] or None)
        }
        try:
            # docker will treat an unknown plolicy as "never".
            # We error out here, in case new policies are added.
            return POLICIES[data[u"Name"]](data)
        except KeyError:
            raise ValueError("Unknown restart policy: %r" % (data[u"Name"],))

    def _serialize_restart_policy(self, restart_policy):
        """
        Serialize the restart policy from an ``IRestartPolicy`` to the format
        expected by the docker API.

        :param IRestartPolicy restart_policy: The model of the restart policy.

        :returns: A dictionary suitable to pass to docker

        :raises ValueError: if an unknown policy is passed.
        """
        SERIALIZERS = {
            RestartNever: lambda policy:
                {u"Name": u""},
            RestartAlways: lambda policy:
                {u"Name": u"always"},
            RestartOnFailure: lambda policy:
                {u"Name": u"on-failure",
                 u"MaximumRetryCount": policy.maximum_retry_count or 0},
        }
        try:
            return SERIALIZERS[restart_policy.__class__](restart_policy)
        except KeyError:
            raise ValueError("Unknown restart policy: %r" % (restart_policy,))

    def add(self, unit_name, image_name, ports=None, environment=None,
            volumes=(), mem_limit=None, cpu_shares=None,
            restart_policy=RestartNever()):
        container_name = self._to_container_name(unit_name)

        if environment is not None:
            environment = environment.to_dict()
        if ports is None:
            ports = []

        restart_policy_dict = self._serialize_restart_policy(restart_policy)

        def _create():
            binds = {
                volume.node_path.path: {
                    'bind': volume.container_path.path,
                    'ro': False,
                }
                for volume in volumes
            }
            port_bindings = {
                p.internal_port: p.external_port
                for p in ports
            }
            host_config = create_host_config(
                binds=binds,
                port_bindings=port_bindings,
                restart_policy=restart_policy_dict,
            )
            self._client.create_container(
                name=container_name,
                image=image_name,
                command=None,
                environment=environment,
                ports=[p.internal_port for p in ports],
                mem_limit=mem_limit,
                cpu_shares=cpu_shares,
                host_config=host_config,
            )

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
            self._client.start(container_name)
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
            while True:
                # There is a race condition between a process dying and
                # docker noticing that fact.
                # https://github.com/docker/docker/issues/5165#issuecomment-65753753  # noqa
                # We loop here to let docker notice that the process is dead.
                # Docker will return NOT_MODIFIED (which isn't an error) in
                # that case.
                try:
                    self._client.stop(container_name)
                except APIError as e:
                    if e.response.status_code == NOT_FOUND:
                        # If the container doesn't exist, we swallow the error,
                        # since this method is supposed to be idempotent.
                        break
                    elif e.response.status_code == INTERNAL_SERVER_ERROR:
                        # Docker returns this if the process had died, but
                        # hasn't noticed it yet.
                        continue
                    else:
                        raise
                else:
                    break

            try:
                self._client.remove_container(container_name)
            except APIError as e:
                # If the container doesn't exist, we swallow the error,
                # since this method is supposed to be idempotent.
                if e.response.status_code == NOT_FOUND:
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

                try:
                    data = self._client.inspect_container(i)
                except APIError as e:
                    # The container ID returned by the list API call above, may
                    # have been removed in another thread.
                    if e.response.status_code == NOT_FOUND:
                        continue

                state = (u"active" if data[u"State"][u"Running"]
                         else u"inactive")
                name = data[u"Name"]
                image = data[u"Config"][u"Image"]
                port_bindings = data[u"HostConfig"][u"PortBindings"]
                if port_bindings is not None:
                    ports = self._parse_container_ports(port_bindings)
                else:
                    ports = list()
                volumes = []
                binds = data[u"HostConfig"]['Binds']
                if binds is not None:
                    for bind_config in binds:
                        parts = bind_config.split(':', 2)
                        node_path, container_path = parts[:2]
                        volumes.append(
                            Volume(container_path=FilePath(container_path),
                                   node_path=FilePath(node_path))
                        )
                if name.startswith(u"/" + self.namespace):
                    name = name[1 + len(self.namespace):]
                else:
                    continue
                # Our Unit model counts None as the value for cpu_shares and
                # mem_limit in containers without specified limits, however
                # Docker returns the values in these cases as zero, so we
                # manually convert.
                cpu_shares = data[u"Config"][u"CpuShares"]
                cpu_shares = None if cpu_shares == 0 else cpu_shares
                mem_limit = data[u"Config"][u"Memory"]
                mem_limit = None if mem_limit == 0 else mem_limit
                restart_policy = self._parse_restart_policy(
                    data[U"HostConfig"][u"RestartPolicy"])
                result.add(Unit(
                    name=name,
                    container_name=self._to_container_name(name),
                    activation_state=state,
                    container_image=image,
                    ports=frozenset(ports),
                    volumes=frozenset(volumes),
                    mem_limit=mem_limit,
                    cpu_shares=cpu_shares,
                    restart_policy=restart_policy)
                )
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
    def __init__(self, namespace, base_url=BASE_DOCKER_API_URL):
        """
        :param unicode namespace: Namespace to restrict containers to.
        """
        self._client = DockerClient(
            namespace=BASE_NAMESPACE + namespace + u"--")
