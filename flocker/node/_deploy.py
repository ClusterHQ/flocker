# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
# -*- test-case-name: flocker.node.test.test_deploy -*-

"""
Deploy applications on nodes.
"""

from twisted.internet.defer import gatherResults

from .gear import GearClient, PortMap
from ._model import Application, StateChanges, AttachedVolume
from ..route import make_host_network, Proxy

from twisted.internet.defer import DeferredList


class Deployer(object):
    """
    Start and stop applications.
    """
    def __init__(self, volume_service, gear_client=None, network=None):
        """
        :param VolumeService volume_service: The volume manager for this node.
        :param IGearClient gear_client: The gear client API to use in
            deployment operations. Default ``GearClient``.
        :param INetwork network: The network routing API to use in
            deployment operations. Default is iptables-based implementation.
        """
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
        if application.ports is not None:
            port_maps = map(lambda p: PortMap(internal_port=p.internal_port,
                                              external_port=p.external_port),
                            application.ports)
        else:
            port_maps = []
        return self._gear_client.add(application.name,
                                     application.image.full_name,
                                     ports=port_maps,
                                     )

    def stop_application(self, application):
        """
        Stop and disable the application.

        :param Application application: The ``Application`` to stop.
        :returns: A ``Deferred`` which fires with ``None`` when the application
            has stopped.
        """
        unit_name = application.name
        return self._gear_client.remove(unit_name)

    def discover_node_configuration(self):
        """
        List all the ``Application``\ s running on this node.

        :returns: A ``Deferred`` which fires with a list of ``Application``
            instances.
        """
        volumes = self._volume_service.enumerate()
        volumes.addCallback(lambda volumes: set(
            volume.name for volume in volumes
            if volume.uuid == self._volume_service.uuid))
        d = gatherResults([self._gear_client.list(), volumes])

        def applications_from_units(result):
            units, available_volumes = result

            applications = []
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
                applications.append(Application(name=unit.name,
                                                volume=volume))
            return applications
        d.addCallback(applications_from_units)
        return d

    def calculate_necessary_state_changes(self, desired_state, hostname):
        """
        Work out which changes need to happen to the local state to match
        the given desired state.

        :param Deployment desired_state: The intended configuration of all
            nodes.
        :param unicode hostname: The hostname of the node that this is running
            on.

        :return: A ``Deferred`` which fires with a ``StateChanges`` instance
            specifying which applications must be started and which must be
            stopped.
        """
        existing_proxies = set(self._network.enumerate_proxies())
        desired_proxies = set()
        desired_node_applications = []
        for node in desired_state.nodes:
            if node.hostname == hostname:
                desired_node_applications = node.applications
            else:
                for application in node.applications:
                    for port in application.ports:
                        # XXX also need to do DNS resolution
                        desired_proxies.add(Proxy(ip=node.hostname,
                                                  port=port.external_port))
                        # XXX this is all the proxies needed - before putting
                        # it in StateChanges figure out the difference between
                        # this and existing_proxies



        proxies_to_create = desired_proxies - existing_proxies
        proxies_to_delete = existing_proxies - desired_proxies
        # XXX: This includes stopped units. See
        # https://github.com/ClusterHQ/flocker/issues/208
        d = self.discover_node_configuration()

        def find_differences(current_node_applications):
            # Compare the applications being changed by name only.  Other
            # configuration changes aren't important at this point.
            current_state = {app.name for app in current_node_applications}
            desired_state = {app.name for app in desired_node_applications}

            start_names = desired_state.difference(current_state)
            stop_names = current_state.difference(desired_state)

            start_containers = {
                app for app in desired_node_applications
                if app.name in start_names
            }
            stop_containers = {
                app for app in current_node_applications
                if app.name in stop_names
            }

            return StateChanges(
                applications_to_start=start_containers,
                applications_to_stop=stop_containers,
                proxies_to_create=proxies_to_create,
                proxies_to_delete=proxies_to_delete
            )
        d.addCallback(find_differences)
        return d

    def change_node_state(self, desired_state, hostname):
        """
        Change the local state to match the given desired state.

        :param Deployment desired_state: The intended configuration of all
            nodes.
        :param unicode hostname: The hostname of the node that this is running
            on.
        """
        d = self.calculate_necessary_state_changes(
            desired_state=desired_state,
            hostname=hostname)
        d.addCallback(self._apply_changes)
        return d

    # XXX moved this into its own method so we can test with StateChanges
    # instances directly.
    def _apply_changes(self, necessary_state_changes):
        """
        Apply desired changes.

        :param StateChanges necessary_state_changes: A record of the
            applications which need to be started and stopped on this node.

        :return: A ``Deferred`` that fires when all application start/stop
            operations have finished.
        """
        # for proxy in self._network.enumerate():
        #     self._network.remove(proxy)
        # for proxy in necessary_state_changes.proxies:
        #     self.network.create_proxy_to(proxy.ip, proxy.port)

        # XXX: Errors in these operations should be logged. See
        # https://github.com/ClusterHQ/flocker/issues/296
        results = []
        for application in necessary_state_changes.applications_to_stop:
            results.append(self.stop_application(application))

        for application in necessary_state_changes.applications_to_start:
            results.append(self.start_application(application))

        return DeferredList(
            results, fireOnOneErrback=True, consumeErrors=True)
