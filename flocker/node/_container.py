# Copyright ClusterHQ Inc.  See LICENSE file for details.
# -*- test-case-name: flocker.node.test.test_container -*-

"""
Deploy applications on nodes.
"""

from warnings import warn
from datetime import timedelta

from zope.interface import implementer

from pyrsistent import PClass, field

from eliot import Message, Logger, start_action

from twisted.internet.defer import fail, succeed

from . import IStateChange, in_parallel, sequentially
from ._docker import DockerClient, PortMap, Environment, Volume as DockerVolume

from ..control._model import (
    Application, AttachedVolume, NodeState, DockerImage, Port, Link,
    RestartNever, pset_field, ip_to_uuid,
    )
from ..route import make_host_network, Proxy, OpenPort
from ..common import gather_deferreds

from ._deploy import IDeployer, NodeLocalState


_logger = Logger()


def _eliot_system(part):
    return u"flocker:node:container_deployer:" + part


@implementer(IStateChange)
class StartApplication(PClass):
    """
    Launch the supplied application as a container.

    :ivar Application application: The ``Application`` to create and
        start.

    :ivar NodeState node_state: The state of the node the ``Application``
        is running on.
    """
    application = field(type=Application, mandatory=True)
    node_state = field(type=NodeState, mandatory=True)

    # This (and other eliot_action implementations) uses `start_action` because
    # it was easier than defining a new `ActionType` with a bunch of fields.
    # It might be worth doing that work eventually, though.  Also, this can
    # turn into a regular attribute when the `_logger` argument is no longer
    # required by Eliot.
    @property
    def eliot_action(self):
        return start_action(
            _logger, _eliot_system(u"startapplication"),
            name=self.application.name,
        )

    def run(self, deployer, state_persister):
        application = self.application

        volumes = []
        if application.volume is not None:
            dataset_id = application.volume.manifestation.dataset_id
            volumes.append(DockerVolume(
                container_path=application.volume.mountpoint,
                node_path=self.node_state.paths[dataset_id]))

        if application.ports is not None:
            port_maps = map(lambda p: PortMap(internal_port=p.internal_port,
                                              external_port=p.external_port),
                            application.ports)
        else:
            port_maps = []

        environment = {}

        for link in application.links:
            environment.update(_link_environment(
                protocol=u"tcp",
                alias=link.alias,
                local_port=link.local_port,
                hostname=self.node_state.hostname,
                remote_port=link.remote_port,
                ))

        if application.environment is not None:
            environment.update(application.environment)

        if environment:
            docker_environment = Environment(
                variables=frozenset(environment.iteritems()))
        else:
            docker_environment = None

        return deployer.docker_client.add(
            application.name,
            application.image.full_name,
            ports=port_maps,
            environment=docker_environment,
            volumes=volumes,
            mem_limit=application.memory_limit,
            cpu_shares=application.cpu_shares,
            # The only supported policy is "never".  See FLOC-2449.
            restart_policy=RestartNever(),
            command_line=application.command_line,
        )


def _link_environment(protocol, alias, local_port, hostname, remote_port):
    """
    Generate the environment variables used for defining a docker link.

    Docker containers expect an enviroment variable
    `<alias>_PORT_<local_port>_TCP`` which contains the URL of the remote end
    of a link, as well as parsed variants ``_ADDR``, ``_PORT``, ``_PROTO``.

    :param unicode protocol: The protocol used for the link.
    :param unicode alias: The name of the link.
    :param int local_port: The port the local application expects to access.
    :param unicode hostname: The remote hostname to connect to.
    :param int remote_port: The remote port to connect to.
    """
    alias = alias.upper()
    base = u'%s_PORT_%d_%s' % (alias, local_port, protocol.upper())

    return {
        base: u'%s://%s:%d' % (protocol, hostname, remote_port),
        base + u'_ADDR': hostname,
        base + u'_PORT': u'%d' % (remote_port,),
        base + u'_PROTO': protocol,
    }


@implementer(IStateChange)
class StopApplication(PClass):
    """
    Stop and disable the given application.

    :ivar Application application: The ``Application`` to stop.
    """
    application = field(type=Application, mandatory=True)

    @property
    def eliot_action(self):
        return start_action(
            _logger, _eliot_system(u"stopapplication"),
            name=self.application.name,
        )

    def run(self, deployer, state_persister):
        application = self.application
        unit_name = application.name
        return deployer.docker_client.remove(unit_name)


@implementer(IStateChange)
class SetProxies(PClass):
    """
    Set the ports which will be forwarded to other nodes.

    :ivar ports: A collection of ``Proxy`` objects.
    """
    ports = pset_field(Proxy)

    @property
    def eliot_action(self):
        return start_action(
            _logger, _eliot_system("setproxies"),
            addresses=list(port.serialize() for port in self.ports),
        )

    def run(self, deployer, state_persister):
        results = []
        # XXX: The proxy manipulation operations are blocking. Convert to a
        # non-blocking API. See https://clusterhq.atlassian.net/browse/FLOC-320
        for proxy in deployer.network.enumerate_proxies():
            try:
                deployer.network.delete_proxy(proxy)
            except:
                results.append(fail())
        for proxy in self.ports:
            try:
                deployer.network.create_proxy_to(proxy.ip, proxy.port)
            except:
                results.append(fail())
        return gather_deferreds(results)


@implementer(IStateChange)
class OpenPorts(PClass):
    """
    Set the ports which will have the firewall opened.

    :ivar ports: A list of :class:`OpenPort`s.
    """
    ports = pset_field(OpenPort)

    @property
    def eliot_action(self):
        return start_action(
            _logger, _eliot_system("openports"),
            ports=list(port.port for port in self.ports),
        )

    def run(self, deployer, state_persister):
        results = []
        # XXX: The proxy manipulation operations are blocking. Convert to a
        # non-blocking API. See https://clusterhq.atlassian.net/browse/FLOC-320
        for open_port in deployer.network.enumerate_open_ports():
            try:
                deployer.network.delete_open_port(open_port)
            except:
                results.append(fail())
        for open_port in self.ports:
            try:
                deployer.network.open_port(open_port.port)
            except:
                results.append(fail())
        return gather_deferreds(results)


@implementer(IDeployer)
class ApplicationNodeDeployer(object):
    """
    Discover and calculate changes for applications running on a node.

    :ivar unicode hostname: The hostname of the node that this is running
            on.
    :ivar IDockerClient docker_client: The Docker client API to use in
        deployment operations. Default ``DockerClient``.
    :ivar INetwork network: The network routing API to use in
        deployment operations. Default is iptables-based implementation.
    """
    def __init__(self, hostname, docker_client=None, network=None,
                 node_uuid=None):
        if node_uuid is None:
            # To be removed in https://clusterhq.atlassian.net/browse/FLOC-1795
            warn("UUID is required, this is for backwards compat with existing"
                 " tests only. If you see this in production code that's "
                 "a bug.", DeprecationWarning, stacklevel=2)
            node_uuid = ip_to_uuid(hostname)
        self.node_uuid = node_uuid
        self.hostname = hostname
        if docker_client is None:
            docker_client = DockerClient()
        self.docker_client = docker_client
        if network is None:
            network = make_host_network()
        self.network = network

    def _attached_volume_for_container(
            self, container, path_to_manifestations
    ):
        """
        Infer the Flocker manifestation which is in use by the given container.

        :param flocker.node._docker.Unit container: The container to inspect.
        :param dict path_to_manifestations: A mapping from mount points (as
            ``FilePath``) to identifiers (as ``unicode``) of the datasets that
            are mounted there.

        :return: ``None`` if no Flocker manifestation can be associated with
            the container state.  Otherwise an ``AttachedVolume`` referring to
            that manifestation and the location in the container where it is
            mounted.
        """
        if container.volumes:
            # XXX https://clusterhq.atlassian.net/browse/FLOC-49
            # we only support one volume per container
            # at this time
            # XXX https://clusterhq.atlassian.net/browse/FLOC-773
            # we assume all volumes are datasets
            docker_volume = list(container.volumes)[0]
            try:
                manifestation = path_to_manifestations[
                    docker_volume.node_path]
            except KeyError:
                # Apparently not a dataset we're managing, give up.
                return None
            else:
                return AttachedVolume(
                    manifestation=manifestation,
                    mountpoint=docker_volume.container_path,
                )
        return None

    def _ports_for_container(self, container):
        """
        Determine the network ports that are exposed by the given container.

        :param flocker.node._docker.Unit container: The container to inspect.

        :return: A ``list`` of ``Port`` instances.
        """
        ports = []
        for portmap in container.ports:
            ports.append(Port(
                internal_port=portmap.internal_port,
                external_port=portmap.external_port
            ))
        return ports

    def _environment_for_container(self, container):
        """
        Get the custom environment specified for the container and infer its
        links.

        It would be nice to do these two things separately but links are only
        represented in the container's environment so both steps involve
        inspecting the environment.

        :param flocker.node._docker.Unit container: The container to inspect.

        :return: A two-tuple of the container's links and environment.  Links
            are given as a ``list`` of ``Link`` instances.  Environment is
            given as a ``list`` of two-tuples giving the environment variable
            name and value (as ``bytes``).
        """
        # Improve the factoring of this later.  Separate it into two methods.
        links = []
        environment = []
        if container.environment:
            environment_dict = container.environment.to_dict()
            for label, value in environment_dict.items():
                # <ALIAS>_PORT_<PORTNUM>_TCP_PORT=<value>
                parts = label.rsplit(b"_", 4)
                try:
                    alias, pad_a, port, pad_b, pad_c = parts
                    local_port = int(port)
                except ValueError:
                    # <ALIAS>_PORT_<PORT>_TCP
                    parts = label.rsplit(b"_", 3)
                    try:
                        alias, pad_a, port, pad_b = parts
                    except ValueError:
                        environment.append((label, value))
                        continue
                    if not (pad_a, pad_b) == (b"PORT", b"TCP"):
                        environment.append((label, value))
                    continue
                if (pad_a, pad_b, pad_c) == (b"PORT", b"TCP", b"PORT"):
                    links.append(Link(
                        local_port=local_port,
                        remote_port=int(value),
                        alias=alias,
                    ))
        return links, environment

    def _applications_from_containers(
            self, containers, path_to_manifestations
    ):
        """
        Reconstruct the original application state from the container state
        that resulted from it.

        :param list containers: The Docker containers that exist here.
        :param path_to_manifestations: See ``_attached_volume_for_container``.

        :return: A ``list`` of ``Application`` instances inferred from
            ``containers`` and ``path_to_manifestations``.
        """
        applications = []
        for container in containers:
            image = DockerImage.from_string(container.container_image)
            volume = self._attached_volume_for_container(
                container, path_to_manifestations,
            )
            ports = self._ports_for_container(container)
            links, environment = self._environment_for_container(container)
            applications.append(Application(
                name=container.name,
                image=image,
                ports=frozenset(ports),
                volume=volume,
                environment=environment if environment else None,
                links=frozenset(links),
                memory_limit=container.mem_limit,
                cpu_shares=container.cpu_shares,
                restart_policy=container.restart_policy,
                running=(container.activation_state == u"active"),
                command_line=container.command_line,
            ))
        return applications

    def _nodestate_from_applications(self, applications):
        """
        Construct a ``NodeState`` representing the state of this node given a
        particular set of applications.

        :param list applications: ``Application`` instances representing the
            applications on this node.

        :return: A ``NodeLocalState`` with shared_state_changes() that
            are composed of a single ``NodeState`` representing the application
            state only of this node.
        """
        return NodeLocalState(
            node_state=NodeState(
                uuid=self.node_uuid,
                hostname=self.hostname,
                applications=applications,
                manifestations=None,
                paths=None,
            )
        )

    def discover_state(self, cluster_state, persistent_state):
        """
        List all the ``Application``\ s running on this node.

        The given local state is used to figure out if applications have
        attached volumes that are specific manifestations. If no
        manifestations are known then discovery isn't done and ignorance
        is claimed about applications. This ensures that the information
        returned is accurate, and therefore that convergence is done
        correctly.

        This does mean you can't run an application agent without a
        dataset agent. See
        https://clusterhq.atlassian.net/browse/FLOC-1646.

        :return: A ``Deferred`` which fires with a list containing a
            ``NodeState`` instance with information only about
            ``Application`` and ports. ``NodeState.manifestations`` and
            ``NodeState.paths`` will not be filled in.
        """
        local_state = cluster_state.get_node(self.node_uuid,
                                             hostname=self.hostname)
        if local_state.manifestations is None:
            # Without manifestations we don't know if local applications'
            # volumes are manifestations or not. Rather than return
            # incorrect information leading to possibly erroneous
            # convergence actions, just declare ignorance. Eventually the
            # convergence agent for datasets will discover the information
            # and then we can proceed.
            return succeed(
                NodeLocalState(
                    node_state=NodeState(
                        uuid=self.node_uuid,
                        hostname=self.hostname,
                        applications=None,
                        manifestations=None,
                        paths=None,
                    )
                )
            )

        path_to_manifestations = {
            path: local_state.manifestations[dataset_id]
            for (dataset_id, path)
            in local_state.paths.items()
        }

        applications = self.docker_client.list()
        applications.addCallback(
            self._applications_from_containers, path_to_manifestations
        )
        applications.addCallback(self._nodestate_from_applications)
        return applications

    def _restart_for_volume_change(self, node_state, state, configuration):
        """
        Determine whether the current volume state of an application is
        divergent from the volume configuration for that application in a way
        that merits an application restart right now.

        Many actual divergences are allowed and ignored:

            - The volume metadata.  This metadata only exists in the
              configuration.  It is always missing from the state object.

            - The volume size.  The dataset agent is not reliably capable of
              performing resizes (if we wait for the actual and configured
              sizes to match, we might have to wait forever).

            - The volume's deleted state.  The application will be allowed to
              continue to use a volume that has been marked for deletion until
              the application is explicitly stopped.

        :param NodeState node_state: The known local state of this node.
        :param AttachedVolume state: The known state of the volume of an
            application being considered.  Or ``None`` if it is known not to
            have a volume.
        :param AttachedVolume configuration: The configured state of the volume
            of the application being considered.  Or ``None`` if it is
            configured to not have a volume.

        :return: If the state differs from the configuration in a way which
            needs to be corrected by the convergence agent (for example, the
            application is configured with a volume but is running without
            one), ``True``.  If it does not differ or only differs in the
            allowed ways mentioned above, ``False``.
        """
        def log(restart, reason=None):
            Message.new(
                message_type=_eliot_system(u"restart_for_volume_change"),
                restart=restart,
                state_is_none=state is None,
                configuration_is_none=configuration is None,
                reason=reason,
            ).write()
            return restart

        def restart_if_available(dataset_id):
            """
            Considering that we would like to restart the application with a
            volume using the given dataset_id, determine whether we can
            actually do so at this time.

            If the indicated dataset has no manifestation on this node, we will
            not be able to start the application again after stopping it.  So
            leave it running until such a manifestation exists.

            :param unicode dataset_id: The identifier of the dataset we want.

            :return: If there is a manifestation of the given dataset on this
                node, ``True``.  Otherwise, ``False``.
            """
            if dataset_id in node_state.manifestations:
                # We want it and we have it.
                return log(True, "have configured dataset")
            else:
                # We want it but we don't have it.
                return log(False, "missing configured dataset")

        state_id = getattr(
            getattr(state, "manifestation", None), "dataset_id", None
        )
        config_id = getattr(
            getattr(configuration, "manifestation", None), "dataset_id", None
        )

        if state_id == config_id:
            return log(False, "dataset matches")
        elif config_id is None:
            return log(True, "volume removed")
        else:
            return restart_if_available(config_id)

    def _restart_for_application_change(
        self, node_state, state, configuration
    ):
        """
        Determine whether the current state of an application is divergent from
        the configuration for that application in a way that merits an
        application restart right now.

        Certain differences are not considered divergences:

            - Certain volume differences.  See ``_restart_for_volume_change``.

        :param NodeState node_state: The known local state of this node.
        :param Application state: The current state of the application.
        :param Application configuration: The desired configuration for the
            application.

        :return: If the state differs from the configuration in a way which
            needs to be corrected by the convergence agent (for example,
            different network ports should be exposed), ``True``.  If it does
            not differ or only differs in the allowed ways mentioned above,
            ``False``.
        """
        volume_state = state.volume
        volume_configuration = configuration.volume

        restart_state = volume_state.restart_policy
        # The volume comparison is too complicated to leave up to `!=` below.
        # Check volumes separately.
        # Restart policies don't implement comparison usefully.  See FLOC-2500.
        comparable_state = state.set(volume=None, restart_policy=RestartNever())
        comparable_configuration = configuration.set(
            volume=None, restart_policy=RestartNever())

        return (
            comparable_state != comparable_configuration or

            # Restart policies were briefly supported but they interact poorly
            # with system restarts.  They're disabled now (except for the
            # default policy, "never").  Ignore the Application's configured
            # policy and enforce the "never" policy.  This will change any
            # existing container that was configured with a different policy.
            # See FLOC-2449.
            #
            # Also restart policies don't implement comparison usefully.  See
            # FLOC-2500.
            not isinstance(restart_state, RestartNever) or

            self._restart_for_volume_change(
                node_state, volume_state, volume_configuration
            )
        )

    def calculate_changes(self, desired_configuration, current_cluster_state,
                          local_state):
        """
        Work out which changes need to happen to the local state to match
        the given desired state.

        Currently this involves the following phases:

        1. Change proxies to point to new addresses (should really be
           last, see https://clusterhq.atlassian.net/browse/FLOC-380)
        2. Stop all relevant containers.
        3. Start and restart any containers that should be running
           locally, so long as their required datasets are available.
        """
        # We are a node-specific IDeployer:
        current_node_state = current_cluster_state.get_node(
            self.node_uuid, hostname=self.hostname)
        if current_node_state.applications is None:
            # We don't know current application state, so can't calculate
            # anything. This will be the case if we don't know the local
            # datasets' state yet; see notes in discover_state().
            return sequentially(changes=[])

        phases = []

        desired_proxies = set()
        desired_open_ports = set()
        desired_node_applications = []
        node_states = {node.uuid: node for node in current_cluster_state.nodes}

        for node in desired_configuration.nodes:
            if node.uuid == self.node_uuid:
                desired_node_applications = node.applications
                for application in node.applications:
                    for port in application.ports:
                        desired_open_ports.add(
                            OpenPort(port=port.external_port))
            else:
                for application in node.applications:
                    for port in application.ports:
                        # XXX: also need to do DNS resolution. See
                        # https://clusterhq.atlassian.net/browse/FLOC-322
                        if node.uuid in node_states:
                            desired_proxies.add(Proxy(
                                ip=node_states[node.uuid].hostname,
                                port=port.external_port))

        if desired_proxies != set(self.network.enumerate_proxies()):
            phases.append(SetProxies(ports=desired_proxies))

        if desired_open_ports != set(self.network.enumerate_open_ports()):
            phases.append(OpenPorts(ports=desired_open_ports))

        all_applications = current_node_state.applications

        # Compare the applications being changed by name only.  Other
        # configuration changes aren't important at this point.
        local_application_names = {app.name for app in all_applications}
        desired_local_state = {app.name for app in
                               desired_node_applications}
        # Don't start applications that exist on this node but aren't running;
        # Docker is in charge of restarts (and restarts aren't supported yet
        # anyway; see FLOC-2449):
        start_names = desired_local_state.difference(local_application_names)
        stop_names = {app.name for app in all_applications}.difference(
            desired_local_state)

        start_containers = [
            StartApplication(application=app, node_state=current_node_state)
            for app in desired_node_applications
            if ((app.name in start_names) and
                # If manifestation isn't available yet, don't start:
                # XXX in FLOC-1240 non-primaries should be checked.
                (app.volume is None or
                 app.volume.manifestation.dataset_id in
                 current_node_state.manifestations))
        ]
        stop_containers = [
            StopApplication(application=app) for app in all_applications
            if app.name in stop_names
        ]

        restart_containers = []

        applications_to_inspect = (
            {app.name for app in all_applications} & desired_local_state)
        current_applications_dict = dict(zip(
            [a.name for a in all_applications], all_applications
        ))
        desired_applications_dict = dict(zip(
            [a.name for a in desired_node_applications],
            desired_node_applications
        ))
        for application_name in applications_to_inspect:
            inspect_desired = desired_applications_dict[application_name]
            inspect_current = current_applications_dict[application_name]

            if self._restart_for_application_change(
                current_node_state, inspect_current, inspect_desired
            ):
                restart_containers.append(sequentially(changes=[
                    StopApplication(application=inspect_current),
                    StartApplication(application=inspect_desired,
                                     node_state=current_node_state),
                ]))

        if stop_containers:
            phases.append(in_parallel(changes=stop_containers))
        start_restart = start_containers + restart_containers
        if start_restart:
            phases.append(in_parallel(changes=start_restart))

        return sequentially(changes=phases,
                            sleep_when_empty=timedelta(seconds=5))
