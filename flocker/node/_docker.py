# Copyright ClusterHQ Inc.  See LICENSE file for details.
# -*- test-case-name: flocker.node.test.test_docker -*-

"""
Docker API client.
"""

from __future__ import absolute_import

from datetime import timedelta

from errno import ECONNREFUSED
from socket import error as socket_error
from functools import partial
from itertools import repeat
from time import sleep

from zope.interface import Interface, implementer

from docker import Client
from docker.errors import APIError, NotFound

from eliot import Message, MessageType, Field, start_action

from repoze.lru import LRUCache

from pyrsistent import field, PClass, pset

from requests import Response
from requests.exceptions import ConnectionError
from requests.packages.urllib3.exceptions import ProtocolError

from characteristic import with_cmp

from twisted.python.components import proxyForInterface
from twisted.python.filepath import FilePath
from twisted.internet.defer import succeed, fail
from twisted.internet.threads import deferToThread
from twisted.web.http import NOT_FOUND, INTERNAL_SERVER_ERROR

from ..common import (
    poll_until,
    retry_if, decorate_methods, with_retry, get_default_retry_steps,
)

from ..control._model import (
    RestartNever, RestartAlways, RestartOnFailure, pset_field, pvector_field)


LOG_CACHED_IMAGE = MessageType(
    u"flocker:node:docker:image_from_cache",
    [Field.for_types(u"image", [unicode], "The image ID.")],
    "An image was retrieved from the cache."
)


class AlreadyExists(Exception):
    """A unit with the given name already exists."""


@with_cmp(["address", "apierror"])
class AddressInUse(Exception):
    """
    The listen address for an exposed port was in use and could not be bound.
    """
    def __init__(self, address, apierror):
        """
        :param tuple address: The conventional Python representation of the
            address which could not be bound (eg, an (ipv4 address, port
            number) pair for IPv4 addresses).
        :param APIError apierror: The original Docker API error indicating this
            problem.  Or ``None`` if the error was not derived from the result
            of a Docker API call.
        """
        Exception.__init__(self, address, apierror)
        self.address = address
        self.apierror = apierror


class Environment(PClass):
    """
    A collection of environment variables.

    :ivar frozenset variables: A ``frozenset`` of tuples containing
        key and value pairs representing the environment variables.
    """
    variables = field(mandatory=True)

    def to_dict(self):
        """
        Convert to a dictionary suitable for serialising to JSON and then on to
        the Docker API.

        :return: ``dict`` mapping keys to values.
        """
        return dict(self.variables)


class Volume(PClass):
    """
    A Docker volume.

    :ivar FilePath node_path: The volume's path on the node's
    filesystem.

    :ivar FilePath container_path: The volume's path within the
    container.
    """
    node_path = field(mandatory=True, type=FilePath)
    container_path = field(mandatory=True, type=FilePath)


class PortMap(PClass):
    """
    A record representing the mapping between a port exposed internally by a
    docker container and the corresponding external port on the host.

    :ivar int internal_port: The port number exposed by the container.
    :ivar int external_port: The port number exposed by the host.
    """
    internal_port = field(mandatory=True, type=int)
    external_port = field(mandatory=True, type=int)


class ImageDataCache(PClass):
    """
    A record representing cached image data. The cache only stores
    the data we care about from an inspected image.

    :ivar list command: The image command.
    :ivar list environment: A list of unicode strings representing
        the image's environment variables.
    """
    command = field(mandatory=True, type=(list, type(None)))
    environment = field(mandatory=True, type=(list, type(None)))


class Unit(PClass):
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

    :ivar PSet ports: The ``PortMap`` instances which define how
        connections to ports on the host are routed to ports exposed in
        the container.

    :ivar Environment environment: An ``Environment`` whose variables
        will be supplied to the Docker container or ``None`` if there are no
        environment variables for this container.

    :ivar PSet volumes: ``Volume`` instances, the container's volumes.

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

    :ivar command_line: Custom command to run using the image, a ``PVector``
        of ``unicode``. ``None`` means use default.

    :ivar swappiness: Tunable swappiness of the container.
        Default of 0 disables swap.
    """
    name = field(mandatory=True)
    container_name = field(mandatory=True)
    activation_state = field(mandatory=True)
    container_image = field(mandatory=True, initial=None)
    ports = pset_field(PortMap)
    environment = field(mandatory=True, initial=None)
    volumes = pset_field(Volume)
    mem_limit = field(mandatory=True, initial=None)
    cpu_shares = field(mandatory=True, initial=None)
    restart_policy = field(mandatory=True, initial=RestartNever())
    command_line = pvector_field(unicode, optional=True, initial=None)
    swappiness = field(mandatory=False, initial=0, type=int)


class IDockerClient(Interface):
    """
    A client for the Docker HTTP API.

    Note the difference in semantics between the results of ``add()``
    (firing does not indicate application started successfully)
    vs. ``remove()`` (firing indicates application has finished shutting
    down).
    """

    def add(unit_name, image_name, ports=None, environment=None, volumes=(),
            mem_limit=None, cpu_shares=None, restart_policy=RestartNever(),
            command_line=None, swappiness=0):
        """
        Install and start a new unit.

        Note that callers should not assume success indicates the unit has
        finished starting up.  In addition to asynchronous nature of Docker,
        even if container is up and running the application within it might
        still be starting up, e.g. it may not have bound the external ports
        yet.  As a result the final success of application startup is out of
        scope for this method.

        :param unicode unit_name: The name of the unit to create.
        :param unicode image_name: The Docker image to use for the unit.
        :param list ports: A list of ``PortMap``\ s mapping ports exposed in
            the container to ports exposed on the host.  Default ``None`` means
            that no port mappings will be configured for this unit.  If a
            ``PortMap`` instance's ``external_port`` is set to ``0`` a free
            port will automatically be assigned.  The assigned port will be
            reported for the container in the result of ``IDockerClient.list``.
        :param Environment environment: Environment variables for the
            container.  Default ``None`` means that no environment variables
            will be supplied to the unit.
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
        :param command_line: Custom command to run using the image, a sequence
            of ``unicode``, or ``None`` to use default image command line.
        :param swappiness: Tune container's memory swappiness.
            Default of 0 disables swap.

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


def make_response(code, message):
    """
    Create a ``requests.Response`` with the given response code and message.

    :param int code: The HTTP response code to include in the fake response.
    :param unicode message: The HTTP response message to include in the fake
        response.  The message will be encoded using ASCII.
    """
    response = Response()
    response.status_code = code
    response.reason = message
    return response


@implementer(IDockerClient)
class FakeDockerClient(object):
    """
    In-memory fake that simulates talking to a docker daemon.

    The state the the simulated units is stored in memory.

    :ivar dict _units: See ``units`` of ``__init__``\ .
    :ivar pset _used_ports: A set of integers giving the port numbers which
        will be considered in use.  Attempts to add containers which use these
        ports will fail.
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
        self._used_ports = pset()

    def add(self, unit_name, image_name, ports=frozenset(), environment=None,
            volumes=frozenset(), mem_limit=None, cpu_shares=None,
            restart_policy=RestartNever(), command_line=None, swappiness=0):
        if unit_name in self._units:
            return fail(AlreadyExists(unit_name))
        for port in ports:
            if port.external_port in self._used_ports:
                raise AddressInUse(
                    address=(b"0.0.0.0", port.external_port),
                    apierror=APIError(
                        'fake api response from server',
                        response=make_response(500, 'fake response')),
                )

        all_ports = set(range(2 ** 15, 2 ** 16))
        assigned_ports = []
        for port in ports:
            if port.external_port == 0:
                available_ports = pset(all_ports) - self._used_ports
                assigned = next(iter(available_ports))
                port = port.set(external_port=assigned)
            assigned_ports.append(port)
            self._used_ports = self._used_ports.add(port.external_port)

        self._units[unit_name] = Unit(
            name=unit_name,
            container_name=unit_name,
            container_image=image_name,
            ports=frozenset(assigned_ports),
            environment=environment,
            volumes=frozenset(volumes),
            activation_state=u'active',
            mem_limit=mem_limit,
            cpu_shares=cpu_shares,
            restart_policy=restart_policy,
            command_line=command_line,
            swappiness=swappiness
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


# Basic namespace for Flocker containers:
BASE_NAMESPACE = u"flocker--"


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


@implementer(IDockerClient)
class DockerClient(object):
    """
    Talk to the real Docker server directly.

    Some operations can take a while (e.g. stopping a container), so we
    use a thread pool. See https://clusterhq.atlassian.net/browse/FLOC-718
    for using a custom thread pool.

    :ivar unicode namespace: A namespace prefix to add to container names
        so we don't clobber other applications interacting with Docker.
    :ivar str base_url: URL for connection to the Docker server.
    :ivar int long_timeout: Maximum time in seconds to wait for
        long-running operations, particularly pulling an image.
    :ivar LRUCache _image_cache: Mapped cache of image IDs to their data.
    """
    def __init__(
            self, namespace=BASE_NAMESPACE, base_url=None,
            long_timeout=600):
        self.namespace = namespace
        self._client = dockerpy_client(
            version="1.15", base_url=base_url,
            long_timeout=timedelta(seconds=long_timeout),
        )
        self._image_cache = LRUCache(100)

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

    def _image_not_found(self, apierror):
        """
        Inspect a ``docker.errors.APIError`` to determine if it represents a
        failure to start a container because the container's image wasn't
        found.

        :return: ``True`` if this is the case, ``False`` if the error has
            another cause.
        :rtype: ``bool``
        """
        return apierror.response.status_code == NOT_FOUND

    def _address_in_use(self, apierror):
        """
        Inspect a ``docker.errors.APIError`` to determine if it represents a
        failure to start a container because the container is configured to use
        ports that are already in use on the system.

        :return: If this is the reason, an exception to raise describing the
            problem.  Otherwise, ``None``.
        """
        # Recognize an error (without newline) like:
        #
        # Cannot start container <name>: Error starting userland proxy:
        # listen tcp <ip>:<port>: bind: address already in use
        #
        # Or (without newline) like:
        #
        # Cannot start container <name>: Bind for <ip>:<port> failed:
        # port is already allocated
        #
        # because Docker can't make up its mind about which format to use.
        parts = apierror.explanation.split(b": ")
        if parts[-1] == b"address already in use":
            ip, port = parts[-3].split()[-1].split(b":")
        elif parts[-1] == b"port is already allocated":
            ip, port = parts[-2].split()[2].split(b":")
        else:
            return None
        return AddressInUse(address=(ip, int(port)), apierror=apierror)

    def _image_data(self, image):
        """
        Supply data about an image, by either inspecting it or returning
        cached data if available.

        :param unicode image: The ID of the image.

        :return: ``dict`` representing data about the image properties.
        """
        cached_image = self._image_cache.get(image)
        if cached_image is not None:
            LOG_CACHED_IMAGE(image=image).write()
            return cached_image
        try:
            image_data = self._client.inspect_image(image)
            Message.new(
                message_type="flocker:node:docker:image_inspected",
                image=image
            ).write()
        except APIError as e:
            if e.response.status_code == NOT_FOUND:
                # Image has been deleted, so just fill in some
                # stub data so we can return *something*. This
                # should happen only for stopped containers so
                # some inaccuracy is acceptable.
                # We won't cache stub data though.
                Message.new(
                    message_type="flocker:node:docker:image_not_found",
                    image=image
                ).write()
                image_data = {u"Config": {u"Env": [], u"Cmd": []}}
            else:
                raise
        cached_data = ImageDataCache(
            command=image_data[u"Config"][u"Cmd"],
            environment=image_data[u"Config"][u"Env"]
        )
        self._image_cache.put(image, cached_data)
        Message.new(
            message_type="flocker:node:docker:image_data_cached",
            image=image
        ).write()
        return cached_data

    def add(self, unit_name, image_name, ports=None, environment=None,
            volumes=(), mem_limit=None, cpu_shares=None,
            restart_policy=RestartNever(), command_line=None,
            swappiness=0):
        container_name = self._to_container_name(unit_name)

        if environment is not None:
            environment = environment.to_dict()
        if ports is None:
            ports = []

        restart_policy_dict = self._serialize_restart_policy(restart_policy)

        def _create():
            binds = list(
                # The "Z" mode tells Docker to "relabel file objects" on the
                # volume.  This makes things work when SELinux is enabled, at
                # least in the default configuration on CentOS 7.  See
                # <https://docs.docker.com/reference/commandline/run/>, in the
                # `--volumes-from` section (or just search for SELinux).
                u"{}:{}:Z".format(
                    volume.node_path.path, volume.container_path.path
                )
                for volume in volumes
            )
            port_bindings = {
                p.internal_port: p.external_port
                for p in ports
            }
            host_config = self._client.create_host_config(
                binds=binds,
                port_bindings=port_bindings,
                restart_policy=restart_policy_dict,
            )
            # We're likely to get e.g. pvector, so make sure we're passing
            # in something JSON serializable:
            command_line_values = command_line
            if command_line_values is not None:
                command_line_values = list(command_line_values)

            self._client.create_container(
                name=container_name,
                image=image_name,
                command=command_line_values,
                environment=environment,
                ports=[p.internal_port for p in ports],
                mem_limit=mem_limit,
                cpu_shares=cpu_shares,
                host_config=host_config,
                swappiness=swappiness,
            )

        def _add():
            try:
                _create()
            except APIError as e:
                if self._image_not_found(e):
                    # Pull it and try again
                    self._client.pull(image_name)
                    _create()
                else:
                    # Unrecognized, just raise it.
                    raise

            # Just because we got a response doesn't mean Docker has
            # actually updated any internal state yet! So if e.g. we did a
            # start on this container Docker might well complain it knows
            # not the container of which we speak. To prevent this we poll
            # until it does exist.
            while True:
                try:
                    self._client.start(container_name)
                except NotFound:
                    sleep(0.01)
                else:
                    break

        d = deferToThread(_add)

        def _extract_error(failure):
            failure.trap(APIError)
            code = failure.value.response.status_code
            if code == 409:
                raise AlreadyExists(unit_name)

            in_use = self._address_in_use(failure.value)
            if in_use is not None:
                # We likely can't start the container because its
                # configuration conflicts with something else happening on
                # the system.  Reflect this failure condition in a more
                # easily recognized way.
                raise in_use

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

    def _stop_container(self, container_name):
        """Attempt to stop the given container.

        There is a race condition between a process dying and
        Docker noticing that fact:

        https://github.com/docker/docker/issues/5165#issuecomment-65753753

        If we get an error indicating that this race condition happened,
        return False. This means the caller should try again. If we *do*
        successfully stop the container, return True.

        :raise APIError: If the container failed to stop for some unknown
            reason.
        :return: True if we stopped the container, False otherwise.

        """
        try:
            with start_action(
                action_type='flocker:docker:container_stop',
                container=container_name
            ):
                self._client.stop(container_name)
        except APIError as e:
            if e.response.status_code == NOT_FOUND:
                # If the container doesn't exist, we swallow the error,
                # since this method is supposed to be idempotent.
                return True
            elif e.response.status_code == INTERNAL_SERVER_ERROR:
                # Docker returns this if the process had died, but
                # hasn't noticed it yet.
                return False
            else:
                raise
        return True

    def _remove_container(self, container_name):
        """
        Attempt to remove a container.

        Assumes the given container has already been stopped.

        :param unicode container_name: The fully-namespaced name of the
            container.
        :return: True if we removed the container, False otherwise.
        """
        try:
            # The ``docker.Client.stop`` method sometimes returns a
            # 404 error, even though the container exists.
            # See https://github.com/docker/docker/issues/13088
            # Wait until the container has actually stopped running
            # before attempting to remove it.  Otherwise we are
            # likely to see: 'docker.errors.APIError: 409 Client
            # Error: Conflict ("Conflict, You cannot remove a
            # running container. Stop the container before
            # attempting removal or use -f")'
            # This code should probably be removed once the above
            # issue has been resolved. See [FLOC-1850]
            self._client.wait(container_name)

            with start_action(
                action_type='flocker:docker:container_remove',
                container=container_name
            ):
                self._client.remove_container(container_name)
        except APIError as e:
            if e.response.status_code == NOT_FOUND:
                # If the container doesn't exist, we swallow the error,
                # since this method is supposed to be idempotent.
                return True
            elif e.response.status_code == INTERNAL_SERVER_ERROR:
                # Failure to remove container - see FLOC-3262 for an example.
                return False
            else:
                raise
        return True

    def remove(self, unit_name):
        container_name = self._to_container_name(unit_name)

        def _remove():
            # Previously, this looped forever and didn't pause between loops.
            # We've arbitrarily chosen a wait interval of 0.001 seconds and
            # 1000 retries (i.e. a second of polling). These values may need
            # tuning.
            poll_until(
                partial(self._stop_container, container_name),
                repeat(0.001, 1000))

            # Previously, the container remove was only tried once. Again,
            # these parameters may need tuning.
            poll_until(
                partial(self._remove_container, container_name),
                repeat(0.001, 1000))

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
                    else:
                        raise

                state = (u"active" if data[u"State"][u"Running"]
                         else u"inactive")
                name = data[u"Name"]
                # Since tags (e.g. "busybox") aren't stable, ensure we're
                # looking at the actual image by using the hash:
                image = data[u"Image"]
                image_tag = data[u"Config"][u"Image"]
                command = data[u"Config"][u"Cmd"]
                with start_action(
                    action_type=u"flocker:node:docker:inspect_image",
                    container=i,
                    running=data[u"State"][u"Running"]
                ):
                    image_data = self._image_data(image)
                if image_data.command == command:
                    command = None
                port_bindings = data[u"NetworkSettings"][u"Ports"]
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
                # Retrieve environment variables for this container,
                # disregarding any environment variables that are part
                # of the image, rather than supplied in the configuration.
                unit_environment = []
                container_environment = data[u"Config"][u"Env"]
                if image_data.environment is None:
                    image_environment = []
                else:
                    image_environment = image_data.environment
                if container_environment is not None:
                    for environment in container_environment:
                        if environment not in image_environment:
                            env_key, env_value = environment.split('=', 1)
                            unit_environment.append((env_key, env_value))
                unit_environment = (
                    Environment(variables=frozenset(unit_environment))
                    if unit_environment else None
                )
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
                    container_image=image_tag,
                    ports=frozenset(ports),
                    volumes=frozenset(volumes),
                    environment=unit_environment,
                    mem_limit=mem_limit,
                    cpu_shares=cpu_shares,
                    restart_policy=restart_policy,
                    command_line=command)
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
    def __init__(self, namespace, base_url=None):
        """
        :param unicode namespace: Namespace to restrict containers to.
        """
        self._client = DockerClient(
            namespace=BASE_NAMESPACE + namespace + u"--")
