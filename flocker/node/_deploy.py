# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
# -*- test-case-name: flocker.node.test.test_deploy -*-

"""
Deploy applications on nodes.
"""

from zope.interface import Interface, implementer

from characteristic import attributes

from twisted.internet.defer import gatherResults, fail, succeed

from ._docker import DockerClient, PortMap, Environment, Volume as DockerVolume
from ._model import (
    Application, VolumeChanges, AttachedVolume, VolumeHandoff,
    NodeState,
    )
from ..route import make_host_network, Proxy
from ..volume._ipc import RemoteVolumeManager, standard_node
from ..volume.service import VolumeName
from ..common import gather_deferreds


def _to_volume_name(name):
    """
    Convert unicode name to ``VolumeName`` with ``u"default"`` namespace.

    To be replaced in https://github.com/ClusterHQ/flocker/issues/737 with
    real namespace support.

    :param unicode name: Volume name.

    :return: ``VolumeName`` with default namespace.
    """
    return VolumeName(namespace=u"default", id=name)


class IStateChange(Interface):
    """
    An operation that changes the state of the local node.
    """
    def run(deployer):
        """
        Run the change.

        :param Deployer deployer: The ``Deployer`` to use.

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
                _to_volume_name(application.volume.name))
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
@attributes(["volume"])
class CreateVolume(object):
    """
    Create a new locally-owned volume.

    :ivar AttachedVolume volume: Volume to create.
    """
    def run(self, deployer):
        return deployer.volume_service.create(
            _to_volume_name(self.volume.name))


@implementer(IStateChange)
@attributes(["volume"])
class WaitForVolume(object):
    """
    Wait for a volume to exist and be owned locally.

    :ivar AttachedVolume volume: Volume to wait for.
    """
    def run(self, deployer):
        return deployer.volume_service.wait_for_volume(
            _to_volume_name(self.volume.name))


@implementer(IStateChange)
@attributes(["volume", "hostname"])
class HandoffVolume(object):
    """
    A volume handoff that needs to be performed from this node to another
    node.

    See :cls:`flocker.volume.VolumeService.handoff` for more details.

    :ivar AttachedVolume volume: The volume to hand off.
    :ivar bytes hostname: The hostname of the node to which the volume is
         meant to be handed off.
    """
    def run(self, deployer):
        service = deployer.volume_service
        destination = standard_node(self.hostname)
        return service.handoff(service.get(_to_volume_name(self.volume.name)),
                               RemoteVolumeManager(destination))


@implementer(IStateChange)
@attributes(["volume", "hostname"])
class PushVolume(object):
    """
    A volume push that needs to be performed from this node to another
    node.

    See :cls:`flocker.volume.VolumeService.push` for more details.

    :ivar AttachedVolume volume: The volume to push.
    :ivar bytes hostname: The hostname of the node to which the volume is
         meant to be pushed.
    """
    def run(self, deployer):
        service = deployer.volume_service
        destination = standard_node(self.hostname)
        return service.push(service.get(_to_volume_name(self.volume.name)),
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
        # non-blocking API. See https://github.com/ClusterHQ/flocker/issues/320
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


class Deployer(object):
    """
    Start and stop applications.

    :ivar VolumeService volume_service: The volume manager for this node.
    :ivar IDockerClient docker_client: The Docker client API to use in
        deployment operations. Default ``DockerClient``.
    :ivar INetwork network: The network routing API to use in
        deployment operations. Default is iptables-based implementation.
    """
    def __init__(self, volume_service, docker_client=None, network=None):
        if docker_client is None:
            docker_client = DockerClient()
        self.docker_client = docker_client
        if network is None:
            network = make_host_network()
        self.network = network
        self.volume_service = volume_service

    def discover_node_configuration(self):
        """
        List all the ``Application``\ s running on this node.

        :returns: A ``Deferred`` which fires with a ``NodeState``
            instance.
        """
        # Add real namespace support in
        # https://github.com/ClusterHQ/flocker/issues/737; for now we just
        # strip the namespace since there will only ever be one.
        volumes = self.volume_service.enumerate()
        volumes.addCallback(lambda volumes: set(
            volume.name.id for volume in volumes
            if volume.uuid == self.volume_service.uuid))
        d = gatherResults([self.docker_client.list(), volumes])

        def applications_from_units(result):
            units, available_volumes = result

            running = []
            not_running = []
            for unit in units:
                # XXX: The container_image will be available on the
                # Unit when
                # https://github.com/ClusterHQ/flocker/issues/207 is
                # resolved.
                if unit.name in available_volumes:
                    # XXX Mountpoint is not available, see
                    # https://github.com/ClusterHQ/flocker/issues/289
                    volume = AttachedVolume(name=unit.name, mountpoint=None)
                else:
                    volume = None
                application = Application(name=unit.name,
                                          volume=volume)
                if unit.activation_state == u"active":
                    running.append(application)
                else:
                    not_running.append(application)
            return NodeState(
                running=running,
                not_running=not_running,
                used_ports=self.network.enumerate_used_ports()
            )
        d.addCallback(applications_from_units)
        return d

    def calculate_necessary_state_changes(self, desired_state,
                                          current_cluster_state, hostname):
        """
        Work out which changes need to happen to the local state to match
        the given desired state.

        Currently this involves the following phases:

        1. Change proxies to point to new addresses (should really be
           last, see https://github.com/ClusterHQ/flocker/issues/380)
        2. Stop all relevant containers.
        3. Handoff volumes.
        4. Wait for volumes.
        5. Create volumes.
        6. Start and restart any relevant containers.

        :param Deployment desired_state: The intended configuration of all
            nodes.
        :param Deployment current_cluster_state: The current configuration
            of all nodes. While technically this also includes the current
            node's state, this information may be out of date so we check
            again to ensure we have absolute latest information.
        :param unicode hostname: The hostname of the node that this is running
            on.

        :return: A ``Deferred`` which fires with a ``IStateChange``
            provider.
        """
        phases = []

        desired_proxies = set()
        desired_node_applications = []
        for node in desired_state.nodes:
            if node.hostname == hostname:
                desired_node_applications = node.applications
            else:
                for application in node.applications:
                    for port in application.ports:
                        # XXX: also need to do DNS resolution. See
                        # https://github.com/ClusterHQ/flocker/issues/322
                        desired_proxies.add(Proxy(ip=node.hostname,
                                                  port=port.external_port))
        if desired_proxies != set(self.network.enumerate_proxies()):
            phases.append(SetProxies(ports=desired_proxies))

        d = self.discover_node_configuration()

        def find_differences(current_node_state):
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
                StartApplication(application=app, hostname=hostname)
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
                                                       hostname=hostname)])
                for app in desired_node_applications
                if app.name in not_running
            ]

            # Find any applications with volumes that are moving to or from
            # this node - or that are being newly created by this new
            # configuration.
            volumes = find_volume_changes(hostname, current_cluster_state,
                                          desired_state)

            # Do an initial push of all volumes that are going to move, so
            # that the final push which happens during handoff is a quick
            # incremental push. This should significantly reduces the
            # application downtime caused by the time it takes to copy
            # data.
            if volumes.going:
                phases.append(InParallel(changes=[
                    PushVolume(volume=handoff.volume,
                               hostname=handoff.hostname)
                    for handoff in volumes.going]))

            if stop_containers:
                phases.append(InParallel(changes=stop_containers))
            if volumes.going:
                phases.append(InParallel(changes=[
                    HandoffVolume(volume=handoff.volume,
                                  hostname=handoff.hostname)
                    for handoff in volumes.going]))
            if volumes.coming:
                phases.append(InParallel(changes=[
                    WaitForVolume(volume=volume)
                    for volume in volumes.coming]))
            if volumes.creating:
                phases.append(InParallel(changes=[
                    CreateVolume(volume=volume)
                    for volume in volumes.creating]))
            start_restart = start_containers + restart_containers
            if start_restart:
                phases.append(InParallel(changes=start_restart))

        d.addCallback(find_differences)
        d.addCallback(lambda _: Sequentially(changes=phases))
        return d

    def change_node_state(self, desired_state,
                          current_cluster_state,
                          hostname):
        """
        Change the local state to match the given desired state.

        :param Deployment desired_state: The intended configuration of all
            nodes.
        :param Deployment current_cluster_state: The current configuration
            of all nodes.
        :param unicode hostname: The hostname of the node that this is running
            on.

        :return: ``Deferred`` that fires when the necessary changes are done.
        """
        d = self.calculate_necessary_state_changes(
            desired_state=desired_state,
            current_cluster_state=current_cluster_state,
            hostname=hostname)
        d.addCallback(lambda change: change.run(self))
        return d


def find_volume_changes(hostname, current_state, desired_state):
    """
    Find what actions need to be taken to deal with changes in volume
    location between current state and desired state of the cluster.

    XXX The logic here assumes the mountpoints have not changed,
    and will act unexpectedly if that is the case. See
    https://github.com/ClusterHQ/flocker/issues/351 for more details.

    XXX The logic here assumes volumes are never added or removed to
    existing applications, merely moved across nodes. As a result test
    coverage for those situations is not implemented. See
    https://github.com/ClusterHQ/flocker/issues/352 for more details.

    XXX Comparison is done via volume name, rather than AttachedVolume
    objects, until https://github.com/ClusterHQ/flocker/issues/289 is fixed.

    :param unicode hostname: The name of the node for which to find changes.

    :param Deployment current_state: The old state of the cluster on which the
        changes are based.

    :param Deployment desired_state: The new state of the cluster towards which
        the changes are working.
    """
    desired_volumes = {node.hostname: set(application.volume for application
                                          in node.applications
                                          if application.volume)
                       for node in desired_state.nodes}
    current_volumes = {node.hostname: set(application.volume for application
                                          in node.applications
                                          if application.volume)
                       for node in current_state.nodes}
    local_desired_volumes = desired_volumes.get(hostname, set())
    local_desired_volume_names = set(volume.name for volume in
                                     local_desired_volumes)
    local_current_volume_names = set(volume.name for volume in
                                     current_volumes.get(hostname, set()))
    remote_current_volume_names = set()
    for volume_hostname, current in current_volumes.items():
        if volume_hostname != hostname:
            remote_current_volume_names |= set(
                volume.name for volume in current)

    # Look at each application volume that is going to be running
    # elsewhere and is currently running here, and add a VolumeHandoff for
    # it to `going`.
    going = set()
    for volume_hostname, desired in desired_volumes.items():
        if volume_hostname != hostname:
            for volume in desired:
                if volume.name in local_current_volume_names:
                    going.add(VolumeHandoff(volume=volume,
                                            hostname=volume_hostname))

    # Look at each application volume that is going to be started on this
    # node.  If it was running somewhere else, we want that Volume to be
    # in `coming`.
    coming_names = local_desired_volume_names.intersection(
        remote_current_volume_names)
    coming = set(volume for volume in local_desired_volumes
                 if volume.name in coming_names)

    # For each application volume that is going to be started on this node
    # that was not running anywhere previously, make sure that Volume is
    # in `creating`.
    creating_names = local_desired_volume_names.difference(
        local_current_volume_names | remote_current_volume_names)
    creating = set(volume for volume in local_desired_volumes
                   if volume.name in creating_names)

    return VolumeChanges(going=going, coming=coming, creating=creating)
