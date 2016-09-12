# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for :py:class:`flocker.control._registry`.
"""

from ..testtools import make_istatepersister_tests, InMemoryStatePersister


def make_inmemorystatepersister(test_case):
    """
    Create a ``InMemoryStatePersister`` for use in tests.

    :return: ``tuple`` of ``IStatePersiter`` and 0-argument callable returning
    a ``PersistentState``.
    """
    state_persister = InMemoryStatePersister()
    return state_persister, state_persister.get_state


class InMemoryStatePersisterTests(
    make_istatepersister_tests(make_inmemorystatepersister)
):
    """
    Tests for ``InMemoryStatePersister``.
    """
