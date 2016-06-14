"""
Store information about relationships between configuration and state.
"""

from functools import partial

from zope.interface import Interface, implementer
from twisted.internet.defer import succeed, fail

from ._model import PersistentState, BlockDeviceOwnership


class IStatePersister(Interface):
    """
    Interface for updating ``PersistentState``.
    """

    def record_ownership(dataset_id, blockdevice_id):
        """
        Record that blockdevice_id is the relevant one for given dataset_id.

        Once a record is made no other entry can overwrite the existing
        one; the relationship is hardcoded and permanent. XXX this may
        interact badly with deletion of dataset where dataset_id is
        auto-generated from name, e.g. Docker plugin.
        That is pre-existing issue, though.

        XXX having IBlockDeviceAPI specific method is kinda bogus. Some
        sort of generic method for storing data moving forward?

        :param UUID dataset_id: The dataset being associated with a
            blockdevice.
        :param unicode blockdevice_id: The blockdevice to associate with the
            dataset.

        :raises DatasetAlreadyOwned: if the dataset already has an associated
            blockdevice.
        """


@implementer(IStatePersister)
class InMemoryStatePersister(object):
    """
    An ``IStatePersister`` that persists state in memory.

    :ivar PersistentState _state: The currently persisted state.
    """

    def __init__(self):
        self._state = PersistentState()

    def record_ownership(self, dataset_id, blockdevice_id):
        try:
            self._state = self._state.transform(
                ['blockdevice_ownership'], partial(
                    BlockDeviceOwnership.record_ownership,
                    dataset_id=dataset_id,
                    blockdevice_id=blockdevice_id,
                ),
            )
        except Exception:
            return fail()
        return succeed(None)

    def get_state(self):
        """
        Get the currently persisted state.

        :return PersistentState: The current state.
        """
        return self._state
