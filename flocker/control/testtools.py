# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tools for testing :py:module:`flocker.control`.
"""

from twisted.internet.endpoints import TCP4ServerEndpoint
from twisted.internet.ssl import ClientContextFactory
from twisted.internet.task import Clock
from twisted.test.proto_helpers import MemoryReactor

from ._clusterstate import ClusterStateService
from ._persistence import ConfigurationPersistenceService
from ._protocol import (
    ControlAMPService,
)


__all__ = [
    'build_control_amp_service',
]


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
