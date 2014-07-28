# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
# -*- test-case-name: flocker.node.test.test_deploy -*-

"""
Deploy applications on nodes.
"""

from zope.interface import Interface, implementer

from characteristic import attributes

from twisted.internet.defer import gatherResults, fail, DeferredList, succeed

from .gear import GearClient, PortMap
from ._model import (
    Application, VolumeChanges, AttachedVolume, VolumeHandoff,
    )
from ..route import make_host_network, Proxy


@attributes(["running", "not_running"])
class NodeState(object):
    """
    The current state of a node.

    :ivar running: A ``list`` of ``Application`` instances on this node
        that are currently running or starting up.
    :ivar not_running: A ``list`` of ``Application`` instances on this
        node that are currently shutting down or stopped.
    """


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
        return gatherResults((change.run(deployer) for change in self.changes),
                             consumeErrors=True)


@implementer(IStateChange)
@attributes(["app"])
class StartApplication(object):
    """
    Start an application.
    """
    def run(self, deployer):
        # Logic currently in Deployer.start_application is moved here
        pass

# StopApplication change
# SetProxies change
# CreateVolume, HandoffVolume, WaitForVolume changes


class Deployer(object):
    """
    Start and stop applications.

    :ivar VolumeService volume_service: The volume manager for this node.
    :ivar IGearClient gear_client: The gear client API to use in
        deployment operations. Default ``GearClient``.
    :ivar INetwork network: The network routing API to use in
        deployment operations. Default is iptables-based implementation.
    """
    def __init__(self, volume_service, gear_client=None, network=None):
        if gear_client is None:
            gear_client = GearClient(hostname=u'127.0.0.1')
        self._gear_client = gear_client
        if network is None:
            network = make_host_network()
        self._network = network
        self._volume_service = volume_service

    def start_application(self, application):
        """
        Launch the supplied application as a `gear` unit.

        :param Application application: The ``Application`` to create and
            start.
        :returns: A ``Deferred`` which fires with ``None`` when the application
           has started.
        """
        if application.volume is not None:
            volume = self._volume_service.get(application.volume.name)
            d = volume.expose_to_docker(application.volume.mountpoint)
        else:
            d = succeed(None)

        if application.ports is not None:
            port_maps = map(lambda p: PortMap(internal_port=p.internal_port,
                                              external_port=p.external_port),
                            application.ports)
        else:
            port_maps = []
        d.addCallback(lambda _: self._gear_client.add(
            application.name,
            application.image.full_name,
            ports=port_maps,
        ))
        return d

    def stop_application(self, application):
        """
        Stop and disable the application.

        :param Application application: The ``Application`` to stop.
        :returns: A ``Deferred`` which fires with ``None`` when the application
            has stopped.
        """
        unit_name = application.name
        result = self._gear_client.remove(unit_name)

        def unit_removed(_):
            if application.volume is not None:
                volume = self._volume_service.get(application.volume.name)
                return volume.remove_from_docker()
        result.addCallback(unit_removed)
        return result

    def discover_node_configuration(self):
        """
        List all the ``Application``\ s running on this node.

        :returns: A ``Deferred`` which fires with a ``NodeState``
            instance.
        """
        volumes = self._volume_service.enumerate()
        volumes.addCallback(lambda volumes: set(
            volume.name for volume in volumes
            if volume.uuid == self._volume_service.uuid))
        d = gatherResults([self._gear_client.list(), volumes])

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
                if unit.activation_state in (u"active", u"activating"):
                    running.append(application)
                else:
                    not_running.append(application)
            return NodeState(running=running, not_running=not_running)
        d.addCallback(applications_from_units)
        return d

    def calculate_necessary_state_changes(self, desired_state,
                                          current_cluster_state, hostname):
        """
        Work out which changes need to happen to the local state to match
        the given desired state.

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
        # Change to create a tree of IStateChange providers, using
        # Sequantially and InParallel for overall structure.
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

        # XXX: This includes stopped units. See
        # https://github.com/ClusterHQ/flocker/issues/326
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

            start_containers = {
                app for app in desired_node_applications
                if app.name in start_names
            }
            stop_containers = {
                app for app in all_applications
                if app.name in stop_names
            }
            restart_containers = {
                app for app in desired_node_applications
                if app.name in not_running
            }

            # Find any applications with volumes that are moving to or from
            # this node - or that are being newly created by this new
            # configuration.
            volumes = find_volume_changes(hostname, current_cluster_state,
                                          desired_state)

            return StateChanges(
                applications_to_start=start_containers,
                applications_to_stop=stop_containers,
                applications_to_restart=restart_containers,
                volumes_to_handoff=volumes.going,
                volumes_to_wait_for=volumes.coming,
                volumes_to_create=volumes.creating,
                proxies=desired_proxies,
            )
        d.addCallback(find_differences)
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
        """
        d = self.calculate_necessary_state_changes(
            desired_state=desired_state,
            current_cluster_state=current_cluster_state,
            hostname=hostname)
        d.addCallback(self._apply_changes)
        return d

    def _apply_changes(self, necessary_state_changes):
        """
        Apply desired changes.

        :param StateChanges necessary_state_changes: A record of the
            applications which need to be started and stopped on this node.

        :return: A ``Deferred`` that fires when all application start/stop
            operations have finished.
        """
        # All logic here gets moved to either IStageChange.run
        # implementations or calculate_necessary_state_changes.

        # XXX: Errors in these operations should be logged. See
        # https://github.com/ClusterHQ/flocker/issues/296
        results = []

        # XXX: The proxy manipulation operations are blocking. Convert to a
        # non-blocking API. See https://github.com/ClusterHQ/flocker/issues/320
        for proxy in self._network.enumerate_proxies():
            try:
                self._network.delete_proxy(proxy)
            except:
                results.append(fail())
        for proxy in necessary_state_changes.proxies:
            try:
                self._network.create_proxy_to(proxy.ip, proxy.port)
            except:
                results.append(fail())

        for application in necessary_state_changes.applications_to_stop:
            results.append(self.stop_application(application))

        for application in necessary_state_changes.applications_to_start:
            results.append(self.start_application(application))

        for application in necessary_state_changes.applications_to_restart:
            d = self.stop_application(application)
            d.addCallback(lambda _: self.start_application(application))
            results.append(d)
        return DeferredList(
            results, fireOnOneErrback=True, consumeErrors=True)


def find_volume_changes(hostname, current_state, desired_state):
    """
    Find what actions need to be taking to deal with changes in volume
    location between current state and desired state of the cluster.

    Note that the logic here presumes the mountpoints have not changed,
    and will act unexpectedly if that is the case. See
    https://github.com/ClusterHQ/flocker/issues/351 for more details.

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
    local_current_volumes = current_volumes.get(hostname, set())
    remote_current_volumes = set()
    for volume_hostname, current in current_volumes.items():
        if volume_hostname != hostname:
            remote_current_volumes |= current

    # Look at each application volume that is going to be running
    # elsewhere and is currently running here, and add a VolumeHandoff for
    # it to `going`.
    going = set()
    for volume_hostname, desired in desired_volumes.items():
        if volume_hostname != hostname:
            for volume in desired:
                if volume in local_current_volumes:
                    going.add(VolumeHandoff(volume=volume,
                                            hostname=volume_hostname))

    # Look at each application volume that is going to be started on this
    # node.  If it was running somewhere else, add an AttachedVolume for
    # it to `coming`.
    coming = local_desired_volumes.intersection(remote_current_volumes)

    # For each application volume that is going to be started on this node
    # that was not running anywhere previously, add an AttachedVolume for
    # it to `creating`.
    creating = local_desired_volumes.difference(
        local_current_volumes | remote_current_volumes)

    return VolumeChanges(going=going, coming=coming, creating=creating)
