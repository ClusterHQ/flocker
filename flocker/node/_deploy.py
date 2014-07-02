# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
# -*- test-case-name: flocker.node.test.test_deploy -*-

"""
Deploy applications on nodes.
"""

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

        :param application: The ``Application`` to create and start.
        :returns: A ``Deferred`` which fires with ``None`` when the application
           has started.
        """
        unit_name = application.name
        image_name = application.image.tag
        return self._gear_client.add(unit_name, image_name)

    def stop_container(self, application):
        """
        Stop and disable the application.

        :param application: The ``Application`` to stop.
        :returns: A ``Deferred`` which fires with ``None`` when the application
            has stopped.
        """
        unit_name = application.name
        return self._gear_client.remove(unit_name)
