# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
# -*- test-case-name: flocker.node.test.test_deploy -*-

"""
Deploy applications on nodes.
"""

from .gear import GearClient
from ._model import Application, StateChanges

from twisted.internet.defer import DeferredList


class Deployer(object):
    """
    Start and stop applications.
    """
    def __init__(self, gear_client=None):
        """
        :param IGearClient gear_client: The gear client API to use in
            deployment operations. Default ``GearClient``.
        """
        if gear_client is None:
            gear_client = GearClient(hostname=u'127.0.0.1')
        self._gear_client = gear_client

    def start_application(self, application):
        """
        Launch the supplied application as a `gear` unit.

        :param Application application: The ``Application`` to create and
            start.
        :returns: A ``Deferred`` which fires with ``None`` when the application
           has started.
        """
        return self._gear_client.add(application.name,
                                     application.image.full_name)

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
        d = self._gear_client.list()

        def applications_from_units(units):
            applications = []
            for unit in units:
                # XXX: This currently only populates the Application name. The
                # container_image will be available on the Unit when
                # https://github.com/ClusterHQ/flocker/issues/207 is resolved.
                applications.append(Application(name=unit.name))
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
        desired_node_applications = []
        for node in desired_state.nodes:
            if node.hostname == hostname:
                desired_node_applications = node.applications

        # XXX: This includes stopped units. See
        # https://github.com/ClusterHQ/flocker/issues/208
        d = self.discover_node_configuration()

        def find_differences(current_node_applications):
            current_state = set(current_node_applications)
            desired_state = set(desired_node_applications)

            return StateChanges(
                applications_to_start=desired_state.difference(current_state),
                applications_to_stop=current_state.difference(desired_state)
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

        def start_and_stop_applications(necessary_state_changes):
            dl = []
            for application in necessary_state_changes.applications_to_stop:
                dl.append(self.stop_application(application))

            for application in necessary_state_changes.applications_to_start:
                dl.append(self.start_application(application))
            return DeferredList(dl)

        d.addCallback(start_and_stop_applications)
        return d
