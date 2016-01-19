"""
Store information about relationships between configuration and state.
"""

from zope.interface import Interface, implementer

from ._model import PersistentState, BlockDeviceOwnership


from twisted.internet.defer import succeed


class IStatePersister(Interface):
    """
    XXX Wraps same on-disk persistence mechanism as _persistence.py, but
    stores different information.
    """

    def record_ownership(dataset_id, blockdevice_id):
        """
        Record that blockdevice_id is the relevant one for given dataset_id.

        Once a record is made no other entry can overwrite the existing
        one; the relationship is hardcoded and permanent. XXX this may
        interact badly with deletion of dataset where dataset_id is
        auto-generated from name, e.g. flocker-deploy or Docker
        plugin. That is pre-existing issue, though.

        XXX having IBlockDeviceAPI specific method is kinda bogus. Some
        sort of generic method for storing data moving forward?
        """
        # Check persisted value, if not already set override and save to
        # disk, otherwise raise error.


@implementer(IStatePersister)
class InMemoryStatePersister(object):
    """
    An ``IStatePersister`` that persists state in memory.

    :ivar PersistentState _state: The currently persisted state.
    """

    def __init__(self):
        self._state = PersistentState()

    def record_ownership(self, dataset_id, blockdevice_id):
        self._state = self._state.transform(
            ['blockdevice_ownership'], partial(
                BlockDeviceOwnership.record_ownership,
                dataset_id=dataset_id,
                blockdevice_id=blockdevice_id,
            ),
        )
        return succeed(None)

    def get_state(self):
        """
        Get the currently persisted state.

        :return PersistentState: The current state.
        """
        return self._state
