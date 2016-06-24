# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tools for testing :py:module:`flocker.control`.
"""
from uuid import uuid4

from zope.interface.verify import verifyObject

from twisted.internet.endpoints import TCP4ServerEndpoint
from twisted.internet.ssl import ClientContextFactory
from twisted.internet.task import Clock
from twisted.python.filepath import FilePath
from twisted.test.proto_helpers import MemoryReactor

from ..testtools import TestCase

from ._clusterstate import ClusterStateService
from ._persistence import ConfigurationPersistenceService
from ._protocol import (
    ControlAMPService, ControlAMP,
)
from ._registry import IStatePersister, InMemoryStatePersister
from ._model import (
    Application,
    AttachedVolume,
    Dataset,
    DatasetAlreadyOwned,
    Deployment,
    DockerImage,
    Lease,
    Manifestation,
    Node,
    PersistentState,
    Port,
)

from ..testtools.amp import (
    LoopbackAMPClient,
)

from hypothesis import given, assume
import hypothesis.strategies as st
from hypothesis.strategies import uuids, text, composite
from hypothesis.extra.datetime import datetimes

__all__ = [
    'build_control_amp_service',
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
        def test_records_blockdeviceid(self, dataset_id, blockdevice_id):
            """
            Calling ``record_ownership`` records the blockdevice
            mapping in the state.
            """
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

        @given(
            dataset_id=uuids(),
            blockdevice_id=text(),
            other_blockdevice_id=text()
        )
        def test_duplicate_blockdevice_id(
            self, dataset_id, blockdevice_id, other_blockdevice_id
        ):
            """
            Calling ``record_ownership`` raises
            ``DatasetAlreadyOwned`` if the dataset already has a
            associated blockdevice.
            """
            assume(blockdevice_id != other_blockdevice_id)
            state_persister, get_state = fixture(self)
            self.successResultOf(state_persister.record_ownership(
                dataset_id=dataset_id,
                blockdevice_id=blockdevice_id,
            ))
            self.failureResultOf(state_persister.record_ownership(
                dataset_id=dataset_id,
                blockdevice_id=other_blockdevice_id,
            ), DatasetAlreadyOwned)
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


def make_loopback_control_client(test_case, reactor):
    """
    Create a control service and a client connected to it.

    :return: A tuple of a ``ControlAMPService`` and a
        ``LoopbackAMPClient`` connected to it.
    """
    control_amp_service = build_control_amp_service(test_case, reactor=reactor)
    client = LoopbackAMPClient(
        command_locator=ControlAMP(reactor, control_amp_service).locator,
    )
    return control_amp_service, client


@composite
def unique_name_strategy(draw):
    """
    A hypothesis strategy to generate an always unique name.
    """
    return unicode(draw(st.uuids()))


@composite
def persistent_state_strategy(draw):
    """
    A hypothesis strategy to generate a ``PersistentState``

    Presently just returns and empty ``PersistentState``
    """
    return PersistentState()


@composite
def lease_strategy(draw, dataset_id=st.uuids(), node_id=st.uuids()):
    """
    A hypothesis strategy to generate a ``Lease``

    :param dataset_id: A strategy to use to create the dataset_id for the
        Lease.

    :param node_id: A strategy to use to create the node_id for the Lease.
    """
    return Lease(
        dataset_id=draw(dataset_id),
        node_id=draw(node_id),
        expiration=draw(datetimes())
    )


@composite
def docker_image_strategy(
        draw,
        repository_strategy=unique_name_strategy(),
        tag_strategy=unique_name_strategy(),
):
    """
    A hypothesis strategy to generate a ``DockerImage``

    :param repository_strategy: A strategy to use to create the repository for
        the ``DockerImage``

    :param tag: A strategy to use to create the repository for the
        ``DockerImage``
    """
    return DockerImage(
        repository=draw(repository_strategy),
        tag=draw(tag_strategy)
    )


@composite
def application_strategy(draw, min_number_of_ports=0, stateful=False):
    """
    A hypothesis strategy to generate an ``Application``

    :param int min_number_of_ports: The minimum number of ports that the
        Application should have.
    """
    num_ports = draw(
        st.integers(
            min_value=min_number_of_ports,
            max_value=max(8, min_number_of_ports+1)
        )
    )
    dataset_id = unicode(uuid4())
    application = Application(
        name=draw(unique_name_strategy()),
        image=draw(docker_image_strategy()),
        ports=frozenset(
            Port(
                internal_port=8000+i,
                external_port=8000+i+1
            ) for i in xrange(num_ports)
        ),
    )
    if stateful:
        application = application.set(
            'volume',
            AttachedVolume(
                manifestation=Manifestation(
                    dataset=Dataset(
                        dataset_id=dataset_id,
                        deleted=False,
                    ),
                    primary=True,
                ),
                mountpoint=FilePath('/flocker').child(dataset_id)
            )
        )
    return application


@composite
def node_strategy(
        draw,
        min_number_of_applications=0,
        stateful_applications=False,
        uuid=st.uuids(),
        applications=application_strategy()
):
    """
    A hypothesis strategy to generate a ``Node``

    :param uuid: The strategy to use to generate the Node's uuid.

    :param applications: The strategy to use to generate the applications on
        the Node.
    """
    applications = {
        a.name: a for a in
        draw(
            st.lists(
                application_strategy(stateful=stateful_applications),
                min_size=min_number_of_applications,
                average_size=2,
                max_size=5
            )
        )
    }
    return Node(
        uuid=draw(uuid),
        applications=applications,
        manifestations={
            a.volume.manifestation.dataset_id: a.volume.manifestation
            for a in applications.values()
            if a.volume is not None
        }
    )


@composite
def node_uuid_pool_strategy(draw, min_number_of_nodes=1):
    """
    A strategy to create a pool of node uuids.

    :param min_number_of_nodes: The minimum number of nodes to create.

    :returns: A strategy to create an iterable of node uuids.
    """
    max_number_of_nodes = max(min_number_of_nodes, 10)
    return draw(
        st.lists(
            uuids(),
            min_size=min_number_of_nodes,
            max_size=max_number_of_nodes
        )
    )


@composite
def deployment_strategy(
        draw,
        min_number_of_nodes=1,
        node_uuid_pool=None,
):
    """
    A hypothesis strategy to generate a ``Deployment``.

    :param int min_number_of_nodes: The minimum number of nodes to have in the
        deployment.

    :param node_uuid_pool: At iterable of node uuids to draw the node uuids for
        the deployment from.
    """
    if node_uuid_pool is None:
        node_uuid_pool = draw(
            node_uuid_pool_strategy(min_number_of_nodes)
        )

    max_number_of_nodes = len(node_uuid_pool)
    node_uuids = list(
        node_uuid_pool[i]
        for i in draw(
            st.sets(
                st.integers(min_value=0, max_value=(max_number_of_nodes-1)),
                min_size=min_number_of_nodes,
                average_size=max(min_number_of_nodes,
                                 int(0.9*max_number_of_nodes)),
                max_size=max_number_of_nodes
            )
        )
    )

    nodes = list(
        draw(node_strategy(uuid=st.just(uuid))) for uuid in node_uuids
    )

    dataset_id_node_mapping = {}
    for node in nodes:
        for dataset_id in node.manifestations:
            dataset_id_node_mapping[dataset_id] = node.uuid

    lease_indexes = []
    if len(dataset_id_node_mapping) > 0:
        lease_indexes = draw(st.sets(
            st.integers(
                min_value=0, max_value=(len(dataset_id_node_mapping)-1)
            )
        ))
    leases = [
        draw(
            lease_strategy(
                dataset_id=st.just(dataset_id),
                node_id=st.just(node_uuid)
            )
        ) for dataset_id, node_uuid in (
            dataset_id_node_mapping.items()[i] for i in lease_indexes
        )
    ]
    persistent_state = draw(persistent_state_strategy())
    return Deployment(
        nodes={n.uuid: n for n in nodes},
        leases={l.dataset_id: l for l in leases},
        persistent_state=persistent_state
    )


@composite
def related_deployments_strategy(draw, number_of_deployments):
    """
    A strategy to generate more than 1 unique deployments that are related.

    Specifically, this ensures that:
    * all node uuids are drawn from a common pool for all of the deployments.
    * deployments contains unique deployements

    :param int number_of_deployments: The number of deployments to create.

    :returns: A strategy to create ``number_of_deployments`` ``Deployment`` s.
    """
    node_uuid_pool = draw(node_uuid_pool_strategy())
    deployments = set()
    while True:
        deployments.add(
            draw(deployment_strategy(node_uuid_pool=node_uuid_pool))
        )
        if len(deployments) == number_of_deployments:
            return tuple(deployments)
