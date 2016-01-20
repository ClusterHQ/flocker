# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tools for testing :py:module:`flocker.control`.
"""

from zope.interface.verify import verifyObject

from twisted.internet.ssl import ClientContextFactory

from ..testtools import TestCase

from ._clusterstate import ClusterStateService
from ._persistence import ConfigurationPersistenceService
from ._protocol import (
    ControlAMPService, ControlServiceLocator, Timeout,
)
from ._registry import IStatePersister, InMemoryStatePersister

from .test.test_protocol import (
    LoopbackAMPClient,
)


__all__ = [
    'InMemoryStatePersister',
    'make_istatepersister_tests',
    'make_loopback_control_client',
]


def make_istatepersister_tests(fixture):
    """
    Create a TestCase for ``IStatePersister``.

    :param fixture: A fixture that returns a tuple of
    :class:`IStatePersister` provider and a 0-argument callable that
        returns a ``PersistentState``.
    """
    class IStatePersisterTests(TestCase):
        """
        Tests for ``IStatePersister`` implementations.
        """

        def test_interface(self):
            """
            The object implements ``IStatePersister``.
            """
            state_persister, get_state = fixture(self)
            verifyObject(IStatePersister, state_persister)

    return IStatePersisterTests


def make_loopback_control_client(test_case, clock):
    """
    Create a control service and a client connected to it.

    :return: A tuple of a ``ControlAMPService`` and a
        ``LoopbackAMPClient`` connected to it.
    """
    from twisted.python.filepath import FilePath
    path = FilePath(test_case.mktemp())
    path.createDirectory()
    persistence_service = ConfigurationPersistenceService(
        reactor=clock,
        path=path,  # path=test_case.make_temporary_directory()
    )
    persistence_service.startService()
    test_case.addCleanup(persistence_service.stopService)

    cluster_state = ClusterStateService(clock)
    cluster_state.startService()
    test_case.addCleanup(cluster_state.stopService)

    control_amp_service = ControlAMPService(
        reactor=clock,
        cluster_state=cluster_state,
        configuration_service=persistence_service,
        endpoint=object(),
        context_factory=ClientContextFactory(),
    )
    # Don't start the control_amp_service, since we don't want to listen
    client = LoopbackAMPClient(
        command_locator=ControlServiceLocator(
            reactor=clock,
            control_amp_service=control_amp_service,
            timeout=Timeout(clock, 1, lambda: None),
        ),
    )
    return control_amp_service, client
