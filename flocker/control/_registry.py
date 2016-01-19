"""
Store information about relationships between configuration and state.
"""

from zope.interface import Interface, implementer

from ._model import PersistentState


class IStatePersister(Interface):
    """
    Interface for updating ``PersistentState``.
    """


@implementer(IStatePersister)
class InMemoryStatePersister(object):
    """
    An ``IStatePersister`` that persists state in memory.

    :ivar PersistentState _state: The currently persisted state.
    """

    def __init__(self):
        self._state = PersistentState()

    def get_state(self):
        """
        Get the currently persisted state.

        :return PersistentState: The current state.
        """
        return self._state
