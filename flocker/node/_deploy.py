# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
# -*- test-case-name: flocker.node.test.test_deploy -*-

"""
Deploy applications on nodes.
"""

from zope.interface import Interface, implementer

from characteristic import attributes

from pyrsistent import pmap

from twisted.internet.defer import gatherResults, fail, succeed

from ._docker import DockerClient, PortMap, Environment, Volume as DockerVolume
from ..control._model import (
    Application, DatasetChanges, AttachedVolume, DatasetHandoff,
    NodeState, DockerImage, Port, Link, Manifestation, Dataset
    )
from ..route import make_host_network, Proxy
from ..volume._ipc import RemoteVolumeManager, standard_node
from ..volume._model import VolumeSize
from ..volume.service import VolumeName
from ..common import gather_deferreds


def _to_volume_name(dataset_id):
    """
    Convert dataset ID to ``VolumeName`` with ``u"default"`` namespace.

    To be replaced in https://clusterhq.atlassian.net/browse/FLOC-737 with
    real namespace support.

    :param unicode dataset_id: Dataset ID.

    :return: ``VolumeName`` with default namespace.
    """
    return VolumeName(namespace=u"default", dataset_id=dataset_id)


class IStateChange(Interface):
    """
    An operation that changes local state.
    """
    def run(deployer):
        """
        Apply the change to local state.

        :param IDeployer deployer: The ``IDeployer`` to use. Specific
            ``IStateChange`` providers may require specific ``IDeployer``
            providers that provide relevant functionality for applying the
            change.

        :return: ``Deferred`` firing when the change is done.
        """

    def __eq__(other):
        """
        Return whether this change is equivalent to another.
        """

    def __ne__(other):
        """
        Return whether this change is not equivalent to another.
        """


class IDeployer(Interface):
    """
    An object that can discover local state and calculate necessary
    changes to bring local state and desired cluster configuration into
    alignment.
    """
    def discover_local_state():
        """
        Discover the local state, i.e. the state which is exclusively under
        the purview of the convergence agent running this instance.

        :return: A ``Deferred`` which fires with an object describing
             local state. This object will be passed to the control
             service (see ``flocker.control._protocol``) and may also be
             passed to this object's
             ``calculate_necessary_state_changes()`` method.
        """

    def calculate_necessary_state_changes(local_state,
                                          desired_configuration,
                                          current_cluster_state):
        """
        Calculate the state changes necessary to make the local state match
        the desired cluster configuration.

        :param local_state: The recent output of ``discover_local_state``.
        :param Deployment desired_configuration: The intended
            configuration of all nodes.
        :param Deployment current_cluster_state: The current state of all
            nodes. While technically this may also includes the local
            state, that information is likely out of date so should be
            overriden by ``local_state``.

        :return: A ``IStateChange`` provider.
        """


@implementer(IStateChange)
@attributes(["changes"])
class Sequentially(object):
    """
    Run a series of changes in sequence, one after the other.

    Failures in earlier changes stop later changes.
    """
    def run(self, deployer):
        d = succeed(None)
        for change in self.changes:
            d.addCallback(lambda _, change=change: change.run(deployer))
        return d


@implementer(IStateChange)
@attributes(["changes"])
class InParallel(object):
    """
    Run a series of changes in parallel.

    Failures in one change do not prevent other changes from continuing.
    """
    def run(self, deployer):
        return gather_deferreds(
            [change.run(deployer) for change in self.changes])


@implementer(IStateChange)
@attributes(["application", "hostname"])
class StartApplication(object):
    """
    Launch the supplied application as a container.

    :ivar Application application: The ``Application`` to create and
        start.

    :ivar unicode hostname: The hostname of the application is running on.
    """
    def run(self, deployer):
        application = self.application

        volumes = []
        if application.volume is not None:
            volume = deployer.volume_service.get(
                _to_volume_name(
                    application.volume.manifestation.dataset.dataset_id))
            volumes.append(DockerVolume(
                container_path=application.volume.mountpoint,
                node_path=volume.get_filesystem().get_path()))

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
                hostname=self.hostname,
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
    alias = alias.upper().replace(u'-', u"_")
    base = u'%s_PORT_%d_%s' % (alias, local_port, protocol.upper())

    return {
        base: u'%s://%s:%d' % (protocol, hostname, remote_port),
        base + u'_ADDR': hostname,
        base + u'_PORT': u'%d' % (remote_port,),
        base + u'_PROTO': protocol,
    }


@implementer(IStateChange)
@attributes(["application"])
class StopApplication(object):
    """
    Stop and disable the given application.

    :ivar Application application: The ``Application`` to stop.
    """
    def run(self, deployer):
        application = self.application
        unit_name = application.name
        return deployer.docker_client.remove(unit_name)


@implementer(IStateChange)
@attributes(["dataset"])
class CreateDataset(object):
    """
    Create a new locally-owned dataset.

    :ivar Dataset dataset: Dataset to create.
    """
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
    def run(self, deployer):
        volume = deployer.volume_service.get(
            name=_to_volume_name(self.dataset.dataset_id),
            size=VolumeSize(maximum_size=self.dataset.maximum_size)
        )
        return deployer.volume_service.set_maximum_size(volume)


@implementer(IStateChange)
@attributes(["dataset"])
class WaitForDataset(object):
    """
    Wait for a dataset to exist and be owned locally.

    :ivar Dataset dataset: Dataset to wait for.
    """
    def run(self, deployer):
        return deployer.volume_service.wait_for_volume(
            _to_volume_name(self.dataset.dataset_id))


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
    def run(self, deployer):
        service = deployer.volume_service
        destination = standard_node(self.hostname)
        return service.push(
            service.get(_to_volume_name(self.dataset.dataset_id)),
            RemoteVolumeManager(destination))


@implementer(IStateChange)
@attributes(["ports"])
class SetProxies(object):
    """
    Set the ports which will be forwarded to other nodes.

    :ivar ports: A collection of ``Port`` objects.
    """
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


@implementer(IDeployer)
class P2PNodeDeployer(object):
    """
    Start and stop applications.

    :ivar unicode hostname: The hostname of the node that this is running
            on.
    :ivar VolumeService volume_service: The volume manager for this node.
    :ivar IDockerClient docker_client: The Docker client API to use in
        deployment operations. Default ``DockerClient``.
    :ivar INetwork network: The network routing API to use in
        deployment operations. Default is iptables-based implementation.
    """
    def __init__(self, hostname, volume_service, docker_client=None,
                 network=None):
        self.hostname = hostname
        if docker_client is None:
            docker_client = DockerClient()
        self.docker_client = docker_client
        if network is None:
            network = make_host_network()
        self.network = network
        self.volume_service = volume_service

    def discover_local_state(self):
        """
        List all the ``Application``\ s running on this node.

        :returns: A ``Deferred`` which fires with a ``NodeState``
            instance.
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
        d = gatherResults([self.docker_client.list(), volumes])

        def applications_from_units(result):
            units, available_manifestations = result
            running = []
            not_running = []
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
                        dataset_id, max_size = available_manifestations.pop(
                            docker_volume.node_path)
                    except KeyError:
                        # Apparently not a dataset we're managing, give up.
                        volume = None
                    else:
                        volume = AttachedVolume(
                            manifestation=Manifestation(
                                dataset=Dataset(
                                    dataset_id=dataset_id,
                                    metadata=pmap({u"name": unit.name}),
                                    maximum_size=max_size),
                                primary=True),
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
                if unit.environment:
                    environment_dict = unit.environment.to_dict()
                    for label, value in environment_dict.items():
                        # <ALIAS>_PORT_<PORTNUM>_TCP_PORT=<value>
                        parts = label.rsplit(b"_", 4)
                        try:
                            alias, pad_a, port, pad_b, pad_c = parts
                            local_port = int(port)
                        except ValueError:
                            continue
                        if (pad_a, pad_b, pad_c) == (b"PORT", b"TCP", b"PORT"):
                            links.append(Link(
                                local_port=local_port,
                                remote_port=int(value),
                                alias=alias,
                            ))
                application = Application(
                    name=unit.name,
                    image=image,
                    ports=frozenset(ports),
                    volume=volume,
                    links=frozenset(links),
                    restart_policy=unit.restart_policy,
                )
                if unit.activation_state == u"active":
                    running.append(application)
                else:
                    not_running.append(application)

            # Any manifestations left over are unattached to any application:
            other_manifestations = frozenset((
                Manifestation(dataset=Dataset(dataset_id=dataset_id,
                                              maximum_size=maximum_size),
                              primary=True)
                for (dataset_id, maximum_size) in
                available_manifestations.values()))
            return NodeState(
                hostname=self.hostname,
                running=running,
                not_running=not_running,
                used_ports=self.network.enumerate_used_ports(),
                other_manifestations=other_manifestations,
            )
        d.addCallback(applications_from_units)
        return d

    def calculate_necessary_state_changes(self, local_state,
                                          desired_configuration,
                                          current_cluster_state):
        """
        Work out which changes need to happen to the local state to match
        the given desired state.

        Currently this involves the following phases:

        1. Change proxies to point to new addresses (should really be
           last, see https://clusterhq.atlassian.net/browse/FLOC-380)
        2. Stop all relevant containers.
        3. Handoff volumes.
        4. Wait for volumes.
        5. Create volumes.
        6. Start and restart any relevant containers.

        :param NodeState local_state: The local state of the node.
        :param Deployment desired_configuration: The intended
            configuration of all nodes.
        :param Deployment current_cluster_state: The current configuration
            of all nodes. While technically this also includes the current
            node's state, this information may be out of date so we check
            again to ensure we have absolute latest information.
        :param unicode hostname: The hostname of the node that this is running
            on.

        :return: A ``IStateChange`` provider.
        """
        # Current cluster state is likely out of date as regards the
        # local state, so update it accordingly:
        current_cluster_state = current_cluster_state.update_node(
            local_state.to_node())

        phases = []

        desired_proxies = set()
        desired_node_applications = []
        for node in desired_configuration.nodes:
            if node.hostname == self.hostname:
                desired_node_applications = node.applications
            else:
                for application in node.applications:
                    for port in application.ports:
                        # XXX: also need to do DNS resolution. See
                        # https://clusterhq.atlassian.net/browse/FLOC-322
                        desired_proxies.add(Proxy(ip=node.hostname,
                                                  port=port.external_port))
        if desired_proxies != set(self.network.enumerate_proxies()):
            phases.append(SetProxies(ports=desired_proxies))

        # We are a node-specific IDeployer:
        current_node_state = local_state
        current_node_applications = current_node_state.running
        all_applications = (current_node_state.running +
                            current_node_state.not_running)

        # Compare the applications being changed by name only.  Other
        # configuration changes aren't important at this point.
        current_state = {app.name for app in current_node_applications}
        desired_local_state = {app.name for app in
                               desired_node_applications}
        not_running = {app.name for app in current_node_state.not_running}

        # Don't start applications that exist on this node but aren't
        # running; instead they should be restarted:
        start_names = desired_local_state.difference(
            current_state | not_running)
        stop_names = {app.name for app in all_applications}.difference(
            desired_local_state)

        start_containers = [
            StartApplication(application=app, hostname=self.hostname)
            for app in desired_node_applications
            if app.name in start_names
        ]
        stop_containers = [
            StopApplication(application=app) for app in all_applications
            if app.name in stop_names
        ]
        restart_containers = [
            Sequentially(changes=[StopApplication(application=app),
                                  StartApplication(application=app,
                                                   hostname=self.hostname)])
            for app in desired_node_applications
            if app.name in not_running
        ]

        applications_to_inspect = current_state & desired_local_state
        current_applications_dict = dict(zip(
            [a.name for a in current_node_applications],
            current_node_applications
        ))
        desired_applications_dict = dict(zip(
            [a.name for a in desired_node_applications],
            desired_node_applications
        ))
        for application_name in applications_to_inspect:
            inspect_desired = desired_applications_dict[application_name]
            inspect_current = current_applications_dict[application_name]
            if inspect_desired != inspect_current:
                changes = [
                    StopApplication(application=inspect_current),
                    StartApplication(application=inspect_desired,
                                     hostname=self.hostname)
                ]
                sequence = Sequentially(changes=changes)
                if sequence not in restart_containers:
                    restart_containers.append(sequence)

        # Find any dataset that are moving to or from this node - or
        # that are being newly created by this new configuration.
        dataset_changes = find_dataset_changes(
            self.hostname, current_cluster_state, desired_configuration)

        if dataset_changes.resizing:
            phases.append(InParallel(changes=[
                ResizeDataset(dataset=dataset)
                for dataset in dataset_changes.resizing]))

        # Do an initial push of all volumes that are going to move, so
        # that the final push which happens during handoff is a quick
        # incremental push. This should significantly reduces the
        # application downtime caused by the time it takes to copy
        # data.
        if dataset_changes.going:
            phases.append(InParallel(changes=[
                PushDataset(dataset=handoff.dataset,
                            hostname=handoff.hostname)
                for handoff in dataset_changes.going]))

        if stop_containers:
            phases.append(InParallel(changes=stop_containers))
        if dataset_changes.going:
            phases.append(InParallel(changes=[
                HandoffDataset(dataset=handoff.dataset,
                               hostname=handoff.hostname)
                for handoff in dataset_changes.going]))
        # any datasets coming to this node should also be
        # resized to the appropriate quota max size once they
        # have been received
        if dataset_changes.coming:
            phases.append(InParallel(changes=[
                WaitForDataset(dataset=dataset)
                for dataset in dataset_changes.coming]))
            phases.append(InParallel(changes=[
                ResizeDataset(dataset=dataset)
                for dataset in dataset_changes.coming]))
        if dataset_changes.creating:
            phases.append(InParallel(changes=[
                CreateDataset(dataset=dataset)
                for dataset in dataset_changes.creating]))
        start_restart = start_containers + restart_containers
        if start_restart:
            phases.append(InParallel(changes=start_restart))
        return Sequentially(changes=phases)


def change_node_state(deployer, desired_configuration,  current_cluster_state):
    """
    Change the local state to match the given desired state.

    :param IDeployer deployer: Deployer to discover local state and
        calculate changes.
    :param Deployment desired_configuration: The intended configuration of all
        nodes.
    :param Deployment current_cluster_state: The current configuration
        of all nodes.

    :return: ``Deferred`` that fires when the necessary changes are done.
    """
    d = deployer.discover_local_state()
    d.addCallback(deployer.calculate_necessary_state_changes,
                  desired_configuration=desired_configuration,
                  current_cluster_state=current_cluster_state)
    d.addCallback(lambda change: change.run(deployer))
    return d


def find_dataset_changes(hostname, current_state, desired_state):
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

    :param unicode hostname: The name of the node for which to find changes.

    :param Deployment current_state: The old state of the cluster on which the
        changes are based.

    :param Deployment desired_state: The new state of the cluster towards which
        the changes are working.

    :return DatasetChanges: Changes to datasets that will be needed in
         order to match desired configuration.
    """
    desired_datasets = {node.hostname:
                        set(manifestation.dataset for manifestation
                            in node.manifestations())
                        for node in desired_state.nodes}
    current_datasets = {node.hostname:
                        set(manifestation.dataset for manifestation
                            in node.manifestations())
                        for node in current_state.nodes}
    local_desired_datasets = desired_datasets.get(hostname, set())
    local_desired_dataset_ids = set(dataset.dataset_id for dataset in
                                    local_desired_datasets)
    local_current_dataset_ids = set(dataset.dataset_id for dataset in
                                    current_datasets.get(hostname, set()))
    remote_current_dataset_ids = set()
    for dataset_hostname, current in current_datasets.items():
        if dataset_hostname != hostname:
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
                for cur_dataset in current_datasets[hostname]:
                    if cur_dataset.dataset_id != new_dataset.dataset_id:
                        continue
                    if cur_dataset.maximum_size != new_dataset.maximum_size:
                        resizing.add(new_dataset)

    # Look at each dataset that is going to be running elsewhere and is
    # currently running here, and add a DatasetHandoff for it to `going`.
    going = set()
    for dataset_hostname, desired in desired_datasets.items():
        if dataset_hostname != hostname:
            for dataset in desired:
                if dataset.dataset_id in local_current_dataset_ids:
                    going.add(DatasetHandoff(dataset=dataset,
                                             hostname=dataset_hostname))

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
    return DatasetChanges(going=going, coming=coming,
                          creating=creating, resizing=resizing)
