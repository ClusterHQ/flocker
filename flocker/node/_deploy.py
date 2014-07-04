# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
# -*- test-case-name: flocker.node.test.test_deploy -*-

"""
Deploy applications on nodes.
"""

from twisted.internet.defer import succeed

from .gear import GearClient


class Deployment(object):
    """
    Start and stop containers.
    """
    def __init__(self, gear_client=None):
        """
        :param IGearClient gear_client: The gear client API to use in
            deployment operations. Default ``GearClient``.
        """
        if gear_client is None:
            gear_client = GearClient(hostname=b'127.0.0.1')
        self._gear_client = gear_client

    def start_container(self, application):
        """
        Launch the supplied application as a `gear` unit.

        :param Application application: The ``Application`` to create and
            start.
        :returns: A ``Deferred`` which fires with ``None`` when the application
           has started.
        """
        return self._gear_client.add(application.name,
                                     application.image.full_name)

    def stop_container(self, application):
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
        """
        return succeed(None)
