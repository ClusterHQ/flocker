# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tools for testing :py:module:`flocker.control`.
"""

from zope.interface.verify import verifyObject

from twisted.internet.endpoints import TCP4ServerEndpoint
from twisted.internet.ssl import ClientContextFactory
from twisted.internet.task import Clock
from twisted.test.proto_helpers import MemoryReactor

from ..testtools import TestCase

from ._clusterstate import ClusterStateService
from ._persistence import ConfigurationPersistenceService
from ._protocol import (
    ControlAMPService, ControlServiceLocator, Timeout,
)
from ._registry import IStatePersister, InMemoryStatePersister

from ..testtools.amp import (
    LoopbackAMPClient,
)

from hypothesis import given
from hypothesis.strategies import uuids, text

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

        @given(
            dataset_id=uuids(),
            blockdevice_id=text(),
        )
        def test_records_blockid(self, dataset_id, blockdevice_id):
            state_persister, get_state = fixture(self)
            d = state_persister.record_ownership(
                dataset_id=dataset_id,
                blockdevice_id=blockdevice_id,
            )
            self.successResultOf(d)
            self.assertEqual(
                get_state().blockdevice_ownership[dataset_id],
                blockdevice_id,
            )

    return IStatePersisterTests


def build_control_amp_service(test_case, reactor=None):
    """
    Create a new ``ControlAMPService``.

    :param TestCase test_case: The test this service is for.

    :return ControlAMPService: Not started.
    """
    if reactor is None:
        reactor = Clock()
    cluster_state = ClusterStateService(reactor)
    cluster_state.startService()
    test_case.addCleanup(cluster_state.stopService)
    persistence_service = ConfigurationPersistenceService(
        reactor, test_case.make_temporary_directory())
    persistence_service.startService()
    test_case.addCleanup(persistence_service.stopService)
    return ControlAMPService(
        reactor, cluster_state, persistence_service,
        TCP4ServerEndpoint(MemoryReactor(), 1234),
        # Easiest TLS context factory to create:
        ClientContextFactory(),
    )


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

    control_amp_service = build_control_amp_service(test_case, reactor=clock)
    # Don't start the control_amp_service, since we don't want to listen
    client = LoopbackAMPClient(
        command_locator=ControlServiceLocator(
            reactor=clock,
            control_amp_service=control_amp_service,
            timeout=Timeout(clock, 1, lambda: None),
        ),
    )
    return control_amp_service, client
