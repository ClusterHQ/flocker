# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""Client implementation for talking to the geard daemon."""


from zope.interface import Interface, implementer

from twisted.internet.defer import succeed, fail


class AlreadyExists(Exception):
    """A unit with the given name already exists."""


class IGearClient(Interface):
    """A client for the geard HTTP API."""

    def add(unit_name, image_name):
        """Install and start a new unit.

        :param unicode unit_name: The name of the unit to create.

        :param unicode image_name: The Docker image to use for the unit.

        :return: ``Deferred`` that fires on success, or errbacks with
            :class:`AlreadyExists` if a unit by that name already exists.
        """

    def exists(unit_name):
        """Check whether the unit exists.

        :param unicode unit_name: The name of the unit to create.

        :return: ``Deferred`` that fires with ``True`` if unit exists,
            otherwise ``False``.
        """

    def remove(unit_name):
        """Stop and delete the given unit.

        This can be done multiple times in the row for the same unit.

        :param unicode unit_name: The name of the unit to stop.

        :return: ``Deferred`` that fires on success.
        """


class GearClient(object):
    """Talk to the gear daemon over HTTP."""


@implementer(IGearClient)
class FakeGearClient(object):
    """In-memory fake that simulates talking to a gear daemon.

    :ivar dict _units: Map ``unicode`` names of added units to dictionary
        containing information about them.
    """

    def __init__(self):
        self._units = {}

    def add(self, unit_name, image_name):
        if unit_name in self._units:
            return fail(AlreadyExists(unit_name))
        self._units[unit_name] = {}
        return succeed(None)

    def exists(self, unit_name):
        return succeed(unit_name in self._units)

    def remove(self, unit_name):
        if unit_name in self._units:
            del self._units[unit_name]
        return succeed(None)
