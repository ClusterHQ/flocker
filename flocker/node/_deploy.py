# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
# -*- test-case-name: flocker.node.test.test_deploy -*-

"""
Deploy applications on nodes.
"""

from itertools import chain
from warnings import warn

from zope.interface import Interface, implementer, Attribute

from characteristic import attributes

from pyrsistent import PRecord, field

from eliot import write_failure, Logger, start_action

from twisted.internet.defer import gatherResults, fail, succeed

from ._docker import DockerClient, PortMap, Environment, Volume as DockerVolume
from . import IStateChange, in_parallel, sequentially

from ..control._model import (
    Application, DatasetChanges, AttachedVolume, DatasetHandoff,
    NodeState, DockerImage, Port, Link, Manifestation, Dataset,
    pset_field, ip_to_uuid
    )
from ..route import make_host_network, Proxy, OpenPort
from ..volume._ipc import RemoteVolumeManager, standard_node
from ..volume._model import VolumeSize
from ..volume.service import VolumeName
from ..common import gather_deferreds


_logger = Logger()


def _to_volume_name(dataset_id):
    """
    Convert dataset ID to ``VolumeName`` with ``u"default"`` namespace.

    To be replaced in https://clusterhq.atlassian.net/browse/FLOC-737 with
    real namespace support.

    :param unicode dataset_id: Dataset ID.

    :return: ``VolumeName`` with default namespace.
    """
    return VolumeName(namespace=u"default", dataset_id=dataset_id)


class IDeployer(Interface):
    """
    An object that can discover local state and calculate necessary
    changes to bring local state and desired cluster configuration into
    alignment.

    :ivar UUID node_uuid: The UUID of the node this deployer is running.
    :ivar unicode hostname: The hostname (really, IP) of the node this
        deployer is managing.
    """
    node_uuid = Attribute("The UUID of thise node, a ``UUID`` instance.")
    hostname = Attribute("The public IP address of this node.")

    def discover_state(local_state):
        """
        Discover the local state, i.e. the state which is exclusively under
        the purview of the convergence agent running this instance.

        :param NodeState local_state: The previously known state of this
            node. This may include information that this deployer cannot
            discover on its own. Information here should NOT be copied
            into the result; the return result should include only
            information discovered by this particular deployer.

        :return: A ``Deferred`` which fires with a tuple of
            ``IClusterStateChange`` providers describing
            local state. These objects will be passed to the control
            service (see ``flocker.control._protocol``) and may also be
            passed to this object's ``calculate_changes()`` method.
        """

    def calculate_changes(configuration, cluster_state):
        """
        Calculate the state changes necessary to make the local state match the
        desired cluster configuration.

        :param Deployment configuration: The intended configuration of all
            nodes.

        :param DeploymentState cluster_state: The current state of all nodes
            already updated with recent output of ``discover_state``.

        :return: An ``IStateChange`` provider.
        """


def _eliot_system(part):
    return u"flocker:p2pdeployer:" + part


@implementer(IStateChange)
class StartApplication(PRecord):
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

    def run(self, deployer):
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
            restart_policy=application.restart_policy,
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
class StopApplication(PRecord):
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

    def run(self, deployer):
        application = self.application
        unit_name = application.name
        return deployer.docker_client.remove(unit_name)


@implementer(IStateChange)
class CreateDataset(PRecord):
    """
    Create a new locally-owned dataset.

    :ivar Dataset dataset: Dataset to create.
    """
    dataset = field(type=Dataset, mandatory=True)

    @property
    def eliot_action(self):
        return start_action(
            _logger, _eliot_system(u"createdataset"),
            dataset_id=self.dataset.dataset_id,
            maximum_size=self.dataset.maximum_size,
        )

    def run(self, deployer):
        volume = deployer.volume_service.get(
            name=_to_volume_name(self.dataset.dataset_id),
            size=VolumeSize(maximum_size=self.dataset.maximum_size)
        )
        return deployer.volume_service.create(volume)


@implementer(IStateChange)
@attributes(["dataset"])
class ResizeDataset(object):
    """
    Resize an existing locally-owned dataset.

    :ivar Dataset dataset: Dataset to resize.
    """
    @property
    def eliot_action(self):
        return start_action(
            _logger, _eliot_system(u"createdataset"),
            dataset_id=self.dataset.dataset_id,
            maximum_size=self.dataset.maximum_size,
        )

    def run(self, deployer):
        volume = deployer.volume_service.get(
            name=_to_volume_name(self.dataset.dataset_id),
            size=VolumeSize(maximum_size=self.dataset.maximum_size)
        )
        return deployer.volume_service.set_maximum_size(volume)


@implementer(IStateChange)
@attributes(["dataset", "hostname"])
class HandoffDataset(object):
    """
    A dataset handoff that needs to be performed from this node to another
    node.

    See :cls:`flocker.volume.VolumeService.handoff` for more details.

    :ivar Dataset dataset: The dataset to hand off.
    :ivar bytes hostname: The hostname of the node to which the dataset is
         meant to be handed off.
    """

    @property
    def eliot_action(self):
        return start_action(
            _logger, _eliot_system(u"handoff"),
            dataset_id=self.dataset.dataset_id,
            hostname=self.hostname,
        )

    def run(self, deployer):
        service = deployer.volume_service
        destination = standard_node(self.hostname)
        return service.handoff(
            service.get(_to_volume_name(self.dataset.dataset_id)),
            RemoteVolumeManager(destination))


@implementer(IStateChange)
@attributes(["dataset", "hostname"])
class PushDataset(object):
    """
    A dataset push that needs to be performed from this node to another
    node.

    See :cls:`flocker.volume.VolumeService.push` for more details.

    :ivar Dataset: The dataset to push.
    :ivar bytes hostname: The hostname of the node to which the dataset is
         meant to be pushed.
    """

    @property
    def eliot_action(self):
        return start_action(
            _logger, _eliot_system(u"push"),
            dataset_id=self.dataset.dataset_id,
            hostname=self.hostname,
        )

    def run(self, deployer):
        service = deployer.volume_service
        destination = standard_node(self.hostname)
        return service.push(
            service.get(_to_volume_name(self.dataset.dataset_id)),
            RemoteVolumeManager(destination))


@implementer(IStateChange)
class DeleteDataset(PRecord):
    """
    Delete all local copies of the dataset.

    A better action would be one that deletes a specific manifestation
    ("volume" in flocker.volume legacy terminology). Unfortunately
    currently "remotely owned volumes" (legacy terminology), aka
    non-primary manifestations or replicas, are not exposed to the
    deployer, so we have to enumerate them here.

    :ivar Dataset dataset: The dataset to delete.
    """
    dataset = field(mandatory=True, type=Dataset)

    @property
    def eliot_action(self):
        return start_action(
            _logger, _eliot_system("delete"),
            dataset_id=self.dataset.dataset_id,
        )

    def run(self, deployer):
        service = deployer.volume_service
        d = service.enumerate()

        def got_volumes(volumes):
            deletions = []
            for volume in volumes:
                if volume.name.dataset_id == self.dataset.dataset_id:
                    deletions.append(service.pool.destroy(volume).addErrback(
                        write_failure, _logger, u"flocker:p2pdeployer:delete"))
            return gatherResults(deletions)
        d.addCallback(got_volumes)
        return d


@implementer(IStateChange)
class SetProxies(PRecord):
    """
    Set the ports which will be forwarded to other nodes.

    :ivar ports: A collection of ``Proxy`` objects.
    """
    ports = pset_field(Proxy)

    @property
    def eliot_action(self):
        return start_action(
            _logger, _eliot_system("setproxies"),
            addresses=list(dict(port) for port in self.ports),
        )

    def run(self, deployer):
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
class OpenPorts(PRecord):
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

    def run(self, deployer):
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


class NotInUseDatasets(object):
    """
    Filter out datasets that are in use by applications.

    For now we delay things like deletion until we know applications
    aren't using the dataset. Later on we'll use leases to decouple
    the application and dataset logic better; see
    https://clusterhq.atlassian.net/browse/FLOC-1425.
    """
    def __init__(self, node_state):
        """
        :param NodeState node_state: Known local state.
        """
        self._in_use_datasets = {app.volume.manifestation.dataset_id
                                 for app in node_state.applications
                                 if app.volume is not None}

    def __call__(self, objects,
                 get_dataset_id=lambda d: unicode(d.dataset_id)):
        """
        Filter out all objects whose dataset_id is in use.

        :param objects: Objects to filter.

        :param get_dataset_id: Callable to extract a ``dataset_id`` from
            an object. By default looks up ``dataset_id`` attribute.

        :return list: Filtered objects.
        """
        result = []
        for obj in objects:
            if get_dataset_id(obj) not in self._in_use_datasets:
                result.append(obj)
        return result


@implementer(IDeployer)
class P2PManifestationDeployer(object):
    """
    Discover and calculate changes for peer-to-peer manifestations (e.g. ZFS)
    on a node.

    :ivar unicode hostname: The hostname of the node that this is running on.
    :ivar VolumeService volume_service: The volume manager for this node.
    """
    def __init__(self, hostname, volume_service, node_uuid=None):
        if node_uuid is None:
            # To be removed in https://clusterhq.atlassian.net/browse/FLOC-1795
            warn("UUID is required, this is for backwards compat with existing"
                 " tests only. If you see this in production code that's "
                 "a bug.", DeprecationWarning, stacklevel=2)
            node_uuid = ip_to_uuid(hostname)
        self.node_uuid = node_uuid
        self.hostname = hostname
        self.volume_service = volume_service

    def discover_state(self, local_state):
        """
        Discover local ZFS manifestations.
        """
        # Add real namespace support in
        # https://clusterhq.atlassian.net/browse/FLOC-737; for now we just
        # strip the namespace since there will only ever be one.
        volumes = self.volume_service.enumerate()

        def map_volumes_to_size(volumes):
            primary_manifestations = {}
            for volume in volumes:
                if volume.node_id == self.volume_service.node_id:
                    # FLOC-1240 non-primaries should be added in too
                    path = volume.get_filesystem().get_path()
                    primary_manifestations[path] = (
                        volume.name.dataset_id, volume.size.maximum_size)
            return primary_manifestations
        volumes.addCallback(map_volumes_to_size)

        def got_volumes(available_manifestations):
            manifestation_paths = {dataset_id: path for (path, (dataset_id, _))
                                   in available_manifestations.items()}

            manifestations = list(
                Manifestation(dataset=Dataset(dataset_id=dataset_id,
                                              maximum_size=maximum_size),
                              primary=True)
                for (dataset_id, maximum_size) in
                available_manifestations.values())

            return [NodeState(
                uuid=self.node_uuid,
                hostname=self.hostname,
                applications=None,
                used_ports=None,
                manifestations={manifestation.dataset_id: manifestation
                                for manifestation in manifestations},
                paths=manifestation_paths,
                devices={},
            )]
        volumes.addCallback(got_volumes)
        return volumes

    def calculate_changes(self, configuration, cluster_state):
        """
        Calculate necessary changes to peer-to-peer manifestations.

        Datasets that are in use by applications cannot be deleted,
        handed-off or resized. See
        https://clusterhq.atlassian.net/browse/FLOC-1425 for leases, a
        better solution.
        """
        local_state = cluster_state.get_node(self.node_uuid)
        # We need to know applications (for now) to see if we should delay
        # deletion or handoffs. Eventually this will rely on leases instead.
        if local_state.applications is None:
            return sequentially(changes=[])
        phases = []

        not_in_use_datasets = NotInUseDatasets(local_state)

        # Find any dataset that are moving to or from this node - or
        # that are being newly created by this new configuration.
        dataset_changes = find_dataset_changes(
            self.node_uuid, cluster_state, configuration)

        resizing = not_in_use_datasets(dataset_changes.resizing)
        if resizing:
            phases.append(in_parallel(changes=[
                ResizeDataset(dataset=dataset)
                for dataset in resizing]))

        going = not_in_use_datasets(dataset_changes.going,
                                    lambda d: d.dataset.dataset_id)
        if going:
            phases.append(in_parallel(changes=[
                HandoffDataset(dataset=handoff.dataset,
                               hostname=handoff.hostname)
                for handoff in going]))

        if dataset_changes.creating:
            phases.append(in_parallel(changes=[
                CreateDataset(dataset=dataset)
                for dataset in dataset_changes.creating]))

        deleting = not_in_use_datasets(dataset_changes.deleting)
        if deleting:
            phases.append(in_parallel(changes=[
                DeleteDataset(dataset=dataset)
                for dataset in deleting
                ]))
        return sequentially(changes=phases)


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

    def discover_state(self, local_state):
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
        if local_state.manifestations is None:
            # Without manifestations we don't know if local applications'
            # volumes are manifestations or not. Rather than return
            # incorrect information leading to possibly erroneous
            # convergence actions, just declare ignorance. Eventually the
            # convergence agent for datasets will discover the information
            # and then we can proceed.
            return succeed([NodeState(
                uuid=self.node_uuid,
                hostname=self.hostname,
                applications=None,
                used_ports=None,
                manifestations=None,
                paths=None,
            )])

        path_to_manifestations = {path: local_state.manifestations[dataset_id]
                                  for (dataset_id, path)
                                  in local_state.paths.items()}
        d = self.docker_client.list()

        def applications_from_units(units):
            applications = []
            for unit in units:
                image = DockerImage.from_string(unit.container_image)
                if unit.volumes:
                    # XXX https://clusterhq.atlassian.net/browse/FLOC-49
                    # we only support one volume per container
                    # at this time
                    # XXX https://clusterhq.atlassian.net/browse/FLOC-773
                    # we assume all volumes are datasets
                    docker_volume = list(unit.volumes)[0]
                    try:
                        manifestation = path_to_manifestations[
                            docker_volume.node_path]
                    except KeyError:
                        # Apparently not a dataset we're managing, give up.
                        volume = None
                    else:
                        volume = AttachedVolume(
                            manifestation=manifestation,
                            mountpoint=docker_volume.container_path)
                else:
                    volume = None
                ports = []
                for portmap in unit.ports:
                    ports.append(Port(
                        internal_port=portmap.internal_port,
                        external_port=portmap.external_port
                    ))
                links = []
                environment = []
                if unit.environment:
                    environment_dict = unit.environment.to_dict()
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
                applications.append(Application(
                    name=unit.name,
                    image=image,
                    ports=frozenset(ports),
                    volume=volume,
                    environment=environment if environment else None,
                    links=frozenset(links),
                    restart_policy=unit.restart_policy,
                    running=(unit.activation_state == u"active"),
                ))

            return [NodeState(
                uuid=self.node_uuid,
                hostname=self.hostname,
                applications=applications,
                used_ports=self.network.enumerate_used_ports(),
                manifestations=None,
                paths=None,
            )]
        d.addCallback(applications_from_units)
        return d

    def calculate_changes(self, desired_configuration, current_cluster_state):
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
        # Don't start applications that exist on this node but aren't
        # running; Docker is in charge of restarts:
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
            # For our purposes what we care about is if configuration has
            # changed, so if it's not running but it's otherwise the same
            # we don't want to do anything:
            comparable_current = inspect_current.transform(["running"], True)
            # Current state never has metadata on datasets, so remove from
            # configuration:
            comparable_desired = inspect_desired
            if comparable_desired.volume is not None:
                comparable_desired = comparable_desired.transform(
                    ["volume", "manifestation", "dataset", "metadata"], {})
            if comparable_desired != comparable_current:
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
        return sequentially(changes=phases)


def find_dataset_changes(uuid, current_state, desired_state):
    """
    Find what actions need to be taken to deal with changes in dataset
    manifestations between current state and desired state of the cluster.

    XXX The logic here assumes the mountpoints have not changed,
    and will act unexpectedly if that is the case. See
    https://clusterhq.atlassian.net/browse/FLOC-351 for more details.

    XXX The logic here assumes volumes are never added or removed to
    existing applications, merely moved across nodes. As a result test
    coverage for those situations is not implemented. See
    https://clusterhq.atlassian.net/browse/FLOC-352 for more details.

    :param UUID uuid: The uuid of the node for which to find changes.

    :param Deployment current_state: The old state of the cluster on which the
        changes are based.

    :param Deployment desired_state: The new state of the cluster towards which
        the changes are working.

    :return DatasetChanges: Changes to datasets that will be needed in
         order to match desired configuration.
    """
    uuid_to_hostnames = {node.uuid: node.hostname
                         for node in current_state.nodes}
    desired_datasets = {node.uuid:
                        set(manifestation.dataset for manifestation
                            in node.manifestations.values())
                        for node in desired_state.nodes}
    current_datasets = {node.uuid:
                        set(manifestation.dataset for manifestation
                            in node.manifestations.values())
                        for node in current_state.nodes}
    local_desired_datasets = desired_datasets.get(uuid, set())
    local_desired_dataset_ids = set(dataset.dataset_id for dataset in
                                    local_desired_datasets)
    local_current_dataset_ids = set(dataset.dataset_id for dataset in
                                    current_datasets.get(uuid, set()))
    remote_current_dataset_ids = set()
    for dataset_node_uuid, current in current_datasets.items():
        if dataset_node_uuid != uuid:
            remote_current_dataset_ids |= set(
                dataset.dataset_id for dataset in current)

    # If a dataset exists locally and is desired anywhere on the cluster, and
    # the desired dataset is a different maximum_size to the existing dataset,
    # the existing local dataset should be resized before any other action
    # is taken on it.
    resizing = set()
    for desired in desired_datasets.values():
        for new_dataset in desired:
            if new_dataset.dataset_id in local_current_dataset_ids:
                for cur_dataset in current_datasets[uuid]:
                    if cur_dataset.dataset_id != new_dataset.dataset_id:
                        continue
                    if cur_dataset.maximum_size != new_dataset.maximum_size:
                        resizing.add(new_dataset)

    # Look at each dataset that is going to be running elsewhere and is
    # currently running here, and add a DatasetHandoff for it to `going`.
    going = set()
    for dataset_node_uuid, desired in desired_datasets.items():
        if dataset_node_uuid != uuid:
            try:
                hostname = uuid_to_hostnames[dataset_node_uuid]
            except KeyError:
                # Apparently we don't know NodeState for this
                # node. Hopefully we'll learn this information eventually
                # but until we do we can't proceed.
                continue
            for dataset in desired:
                if dataset.dataset_id in local_current_dataset_ids:
                    going.add(DatasetHandoff(
                        dataset=dataset, hostname=hostname))

    # Look at each dataset that is going to be hosted on this node.  If it
    # was running somewhere else, we want that dataset to be in `coming`.
    coming_dataset_ids = local_desired_dataset_ids.intersection(
        remote_current_dataset_ids)
    coming = set(dataset for dataset in local_desired_datasets
                 if dataset.dataset_id in coming_dataset_ids)

    # For each dataset that is going to be hosted on this node and did not
    # exist previously, make sure that dataset is in `creating`.
    creating_dataset_ids = local_desired_dataset_ids.difference(
        local_current_dataset_ids | remote_current_dataset_ids)
    creating = set(dataset for dataset in local_desired_datasets
                   if dataset.dataset_id in creating_dataset_ids)

    deleting = set(dataset for dataset in chain(*desired_datasets.values())
                   if dataset.deleted)
    return DatasetChanges(going=going, coming=coming, deleting=deleting,
                          creating=creating, resizing=resizing)
