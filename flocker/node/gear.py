# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""Client implementation for talking to the geard daemon."""


from twisted.interface import Interface


class IGearClient(Interface):
    """A client for the geard HTTP API."""

    def install(unit_name, image_name):
        """Install a new unit.

        :param unicode unit_name: The name of the unit to create.

        :param unicode image_name: The Docker image to use for the unit.

        :return: ``Deferred`` that fires on success, or errbacks with
            :class:`GearError` if an error occurred.
        """

    def start(unit_name):
        """Start the given unit.

        :param unicode unit_name: The name of the unit to start.

        :return: ``Deferred`` that fires on success, or errbacks with
            :class:`GearError` if an error occurred.
        """

    def stop(unit_name):
        """Stop the given unit.

        :param unicode unit_name: The name of the unit to stop.

        :return: ``Deferred`` that fires on success, or errbacks with
            :class:`GearError` if an error occurred.
        """

    def delete(unit_name):
        """Delete the given unit.

        :param unicode unit_name: The name of the unit to remove.

        :return: ``Deferred`` that fires on success, or errbacks with
            :class:`GearError` if an error occurred.
        """


class GearClient(object):
    """Talk to the gear daemon over HTTP."""


class FakeGearClient(object):
    """In-memory fake that simulates talking to a gear daemon."""
