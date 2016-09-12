# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for ``flocker.node._p2p``.
"""


from uuid import UUID, uuid4
from datetime import datetime, timedelta

from pytz import UTC

from eliot.testing import validate_logging

from twisted.internet.defer import fail, Deferred
from twisted.python.filepath import FilePath

from .. import (
    P2PManifestationDeployer, NoOp,
)
from ...control import (
    Application, DockerImage, Deployment, Node,
    NodeState, DeploymentState, PersistentState,
)
from ...control.testtools import InMemoryStatePersister

from .. import sequentially, in_parallel

from .._deploy import (
    NodeLocalState,
)
from .._p2p import (
    CreateDataset, HandoffDataset, PushDataset, ResizeDataset,
    _to_volume_name, DeleteDataset
)
from ...testtools import AsyncTestCase, TestCase, CustomException
from .. import _p2p
from ...control._model import (
    AttachedVolume, Dataset, Manifestation, Leases
)
from ...volume.service import VolumeName
from ...volume._model import VolumeSize
from ...volume.testtools import create_volume_service
from ...volume._ipc import RemoteVolumeManager, standard_node

from .istatechange import make_istatechange_tests

# This models an application that has a volume.
APPLICATION_WITH_VOLUME_NAME = u"psql-clusterhq"
DATASET_ID = unicode(uuid4())
DATASET = Dataset(dataset_id=DATASET_ID)
APPLICATION_WITH_VOLUME_MOUNTPOINT = FilePath(b"/var/lib/postgresql")
APPLICATION_WITH_VOLUME_IMAGE = u"clusterhq/postgresql:9.1"
APPLICATION_WITH_VOLUME = Application(
    name=APPLICATION_WITH_VOLUME_NAME,
    image=DockerImage.from_string(APPLICATION_WITH_VOLUME_IMAGE),
    volume=AttachedVolume(
        manifestation=Manifestation(dataset=DATASET, primary=True),
        mountpoint=APPLICATION_WITH_VOLUME_MOUNTPOINT,
    ),
    links=frozenset(),
)
MANIFESTATION = APPLICATION_WITH_VOLUME.volume.manifestation

DATASET_WITH_SIZE = Dataset(dataset_id=DATASET_ID,
                            metadata=DATASET.metadata,
                            maximum_size=1024 * 1024 * 100)

APPLICATION_WITH_VOLUME_SIZE = Application(
    name=APPLICATION_WITH_VOLUME_NAME,
    image=DockerImage.from_string(APPLICATION_WITH_VOLUME_IMAGE),
    volume=AttachedVolume(
        manifestation=Manifestation(dataset=DATASET_WITH_SIZE,
                                    primary=True),
        mountpoint=APPLICATION_WITH_VOLUME_MOUNTPOINT,
    ),
    links=frozenset(),
)

MANIFESTATION_WITH_SIZE = APPLICATION_WITH_VOLUME_SIZE.volume.manifestation

# Placeholder in case at some point discovered application is different
# than requested application:
DISCOVERED_APPLICATION_WITH_VOLUME = APPLICATION_WITH_VOLUME


_DATASET_A = Dataset(dataset_id=unicode(uuid4()))
_DATASET_B = Dataset(dataset_id=unicode(uuid4()))


CreateDatasetIStateChangeTests = make_istatechange_tests(
    CreateDataset,
    dict(dataset=_DATASET_A),
    dict(dataset=_DATASET_B),
)
HandoffVolumeIStateChangeTests = make_istatechange_tests(
    HandoffDataset,
    dict(dataset=_DATASET_A, hostname=b"123"),
    dict(dataset=_DATASET_B, hostname=b"123")
)
PushVolumeIStateChangeTests = make_istatechange_tests(
    PushDataset,
    dict(dataset=_DATASET_A, hostname=b"123"),
    dict(dataset=_DATASET_B, hostname=b"123")
)
DeleteDatasetTests = make_istatechange_tests(
    DeleteDataset,
    dict(dataset=_DATASET_A),
    dict(dataset=_DATASET_B),
)


# https://clusterhq.atlassian.net/browse/FLOC-1926
EMPTY_NODESTATE = NodeState(hostname=u"example.com", uuid=uuid4(),
                            manifestations={}, devices={}, paths={},
                            applications=[])


class P2PManifestationDeployerDiscoveryTests(TestCase):
    """
    Tests for ``P2PManifestationDeployer`` discovery.
    """
    def setUp(self):
        super(P2PManifestationDeployerDiscoveryTests, self).setUp()
        self.volume_service = create_volume_service(self)
        self.node_uuid = uuid4()
        # https://clusterhq.atlassian.net/browse/FLOC-1926
        self.EMPTY_NODESTATE = NodeState(hostname=u"example.com",
                                         uuid=self.node_uuid)

    DATASET_ID = unicode(uuid4())
    DATASET_ID2 = unicode(uuid4())

    def test_unknown_applications_and_ports(self):
        """
        Applications and ports are left as ``None`` in discovery results.
        """
        deployer = P2PManifestationDeployer(
            u'example.com', self.volume_service, node_uuid=self.node_uuid)
        self.assertEqual(
            self.successResultOf(deployer.discover_state(
                DeploymentState(nodes={self.EMPTY_NODESTATE}),
                persistent_state=PersistentState())).node_state,
            NodeState(hostname=deployer.hostname,
                      uuid=deployer.node_uuid,
                      manifestations={}, paths={}, devices={},
                      applications=None))

    def _setup_datasets(self):
        """
        Setup a ``P2PManifestationDeployer`` that will discover two
        manifestations.

        :return: Suitably configured ``P2PManifestationDeployer``.
        """
        self.successResultOf(self.volume_service.create(
            self.volume_service.get(_to_volume_name(self.DATASET_ID))
        ))
        self.successResultOf(self.volume_service.create(
            self.volume_service.get(_to_volume_name(self.DATASET_ID2))
        ))

        return P2PManifestationDeployer(
            u'example.com',
            self.volume_service,
            node_uuid=self.node_uuid
        )

    def test_uuid(self):
        """
        The ``NodeState`` returned from discovery has same UUID as the
        deployer.
        """
        deployer = self._setup_datasets()
        node_state = self.successResultOf(deployer.discover_state(
            DeploymentState(nodes={self.EMPTY_NODESTATE}),
            persistent_state=PersistentState(),
        )).node_state
        self.assertEqual(node_state.uuid, deployer.node_uuid)

    def test_discover_datasets(self):
        """
        All datasets on the node are added to ``NodeState.manifestations``.
        """
        api = self._setup_datasets()
        d = api.discover_state(DeploymentState(nodes={self.EMPTY_NODESTATE}),
                               persistent_state=PersistentState())

        self.assertEqual(
            {self.DATASET_ID: Manifestation(
                dataset=Dataset(dataset_id=self.DATASET_ID),
                primary=True),
             self.DATASET_ID2: Manifestation(
                 dataset=Dataset(dataset_id=self.DATASET_ID2),
                 primary=True)},
            self.successResultOf(d).node_state.manifestations)

    def test_discover_manifestation_paths(self):
        """
        All datasets on the node have their paths added to
        ``NodeState.manifestations``.
        """
        api = self._setup_datasets()
        d = api.discover_state(DeploymentState(nodes={self.EMPTY_NODESTATE}),
                               persistent_state=PersistentState())

        self.assertEqual(
            {self.DATASET_ID:
             self.volume_service.get(_to_volume_name(
                 self.DATASET_ID)).get_filesystem().get_path(),
             self.DATASET_ID2:
             self.volume_service.get(_to_volume_name(
                 self.DATASET_ID2)).get_filesystem().get_path()},
            self.successResultOf(d).node_state.paths)

    def test_discover_manifestation_with_size(self):
        """
        Manifestation with a locally configured size have their
        ``maximum_size`` attribute set.
        """
        self.successResultOf(self.volume_service.create(
            self.volume_service.get(
                _to_volume_name(self.DATASET_ID),
                size=VolumeSize(maximum_size=1024 * 1024 * 100)
            )
        ))

        manifestation = Manifestation(
            dataset=Dataset(
                dataset_id=self.DATASET_ID,
                maximum_size=1024 * 1024 * 100),
            primary=True,
        )

        api = P2PManifestationDeployer(
            u'example.com',
            self.volume_service,
            node_uuid=self.node_uuid,
        )
        d = api.discover_state(DeploymentState(nodes={self.EMPTY_NODESTATE}),
                               persistent_state=PersistentState())

        self.assertEqual(
            self.successResultOf(d).node_state.manifestations[
                self.DATASET_ID],
            manifestation)


NO_CHANGES = NoOp(sleep=timedelta(seconds=1))


class P2PManifestationDeployerLeaseTests(TestCase):
    """
    Tests for impact of leases on
    ``P2PManifestationDeployer.calculate_changes``.
    """
    NODE_ID = uuid4()
    NODE_ID2 = uuid4()
    NODE_HOSTNAMES = {NODE_ID: u"10.1.1.1", NODE_ID2: u"10.1.2.3"}
    NOW = datetime.now(tz=UTC)

    def changes_when_leased(self, configured, actual,
                            lease_node=NODE_ID,
                            configured_node=NODE_ID,
                            actual_node=NODE_ID):
        """
        Given a lease on a dataset and configuration and state, return
        calculated changes.

        :param Manifestation configured: The configured ``Manifestation``.
        :param Manifestation actual: The ``Manifestation`` in the node's state.
        :param UUID lease_node: Node for which we have lease.
        :param UUID configured_node: Node for which we have configuration.
        :param UUID actual_node: Node for which we have state.

        :return: Result of ``P2PManifestationDeployer.calculate_changes``.
        """
        node = Node(
            uuid=configured_node,
            manifestations={configured.dataset_id: configured})
        desired = Deployment(nodes=[node], leases=Leases().acquire(
            self.NOW, UUID(configured.dataset_id), lease_node))
        other_actual_node = (self.NODE_ID if actual_node is self.NODE_ID2
                             else self.NODE_ID2)
        actual_node_state = NodeState(
            uuid=actual_node, hostname=self.NODE_HOSTNAMES[actual_node],
            applications={}, devices={}, paths={},
            manifestations={actual.dataset_id: actual})
        current = DeploymentState(nodes=[
            actual_node_state,
            # We have state for other node too, so handoffs aren't
            # prevented:
            NodeState(
                uuid=other_actual_node,
                hostname=self.NODE_HOSTNAMES[other_actual_node],
                applications={}, devices={}, paths={},
                manifestations={})])

        api = P2PManifestationDeployer(
            self.NODE_HOSTNAMES[actual_node], create_volume_service(self),
            node_uuid=actual_node,
        )
        return api.calculate_changes(
            desired, current, NodeLocalState(node_state=actual_node_state))

    def test_no_deletion_if_leased(self):
        """
        ``P2PManifestationDeployer.calculate_changes`` ensures dataset
        deletion does not happens if there is a lease on the dataset.
        """
        changes = self.changes_when_leased(
            MANIFESTATION.transform(("dataset", "deleted"), True),
            MANIFESTATION)
        self.assertEqual(NO_CHANGES, changes)

    def test_no_resize_if_leased(self):
        """
        ``P2PManifestationDeployer.calculate_changes`` ensures dataset
        resize does not happens if there is a lease on the dataset.
        """
        changes = self.changes_when_leased(
            MANIFESTATION_WITH_SIZE, MANIFESTATION)
        self.assertEqual(NO_CHANGES, changes)

    def test_no_handoff_if_leased_on_different_node(self):
        """
        ``P2PManifestationDeployer.calculate_changes`` ensures dataset handoff
        does not happens if there is a lease on the dataset and that lease
        is on a different node than the destination.
        """
        changes = self.changes_when_leased(
            MANIFESTATION, MANIFESTATION,
            # lease:       destination:  origin:
            self.NODE_ID2, self.NODE_ID, self.NODE_ID2)
        self.assertEqual(NO_CHANGES, changes)

    def test_handoff_if_leased_on_destination_node(self):
        """
        ``P2PManifestationDeployer.calculate_changes`` results in dataset
        handoff even if there is a lease on the dataset as long as that
        lease is for the same node as the destination.
        """
        changes = self.changes_when_leased(
            MANIFESTATION, MANIFESTATION,
            # lease:       destination:  origin:
            self.NODE_ID, self.NODE_ID, self.NODE_ID2)
        expected = sequentially(changes=[
            in_parallel(changes=[HandoffDataset(
                dataset=MANIFESTATION.dataset,
                hostname=self.NODE_HOSTNAMES[self.NODE_ID])]),
        ])
        self.assertEqual(expected, changes)


class P2PManifestationDeployerCalculateChangesTests(TestCase):
    """
    Tests for
    ``P2PManifestationDeployer.calculate_changes``.
    """
    def test_dataset_deleted(self):
        """
        ``P2PManifestationDeployer.calculate_changes`` specifies that a
        dataset must be deleted if the desired configuration specifies
        that the dataset has the ``deleted`` attribute set to True.

        Note that for now this happens regardless of whether the node
        actually has the dataset, since the deployer doesn't know about
        replicas... see FLOC-1240.
        """
        node_state = NodeState(
            hostname=u"10.1.1.1",
            manifestations={MANIFESTATION.dataset_id:
                            MANIFESTATION},
            devices={}, paths={},
            applications=[],
        )

        api = P2PManifestationDeployer(
            node_state.hostname,
            create_volume_service(self),
        )
        current = DeploymentState(nodes=[node_state])
        desired = Deployment(nodes=[
            Node(hostname=api.hostname,
                 manifestations=node_state.manifestations.transform(
                     (DATASET_ID, "dataset", "deleted"), True))])

        changes = api.calculate_changes(desired, current,
                                        NodeLocalState(node_state=node_state))
        expected = sequentially(changes=[
            in_parallel(changes=[DeleteDataset(dataset=DATASET.set(
                "deleted", True))])
            ])
        self.assertEqual(expected, changes)

    def test_no_deletion_if_in_use(self):
        """
        ``P2PManifestationDeployer.calculate_changes`` ensures dataset
        deletion happens only if there is no application using the deleted
        dataset.

        This will eventually be switched to use a lease system, rather
        than inspecting application configuration.
        """
        node = Node(
            uuid=uuid4(),
            manifestations={
                MANIFESTATION.dataset_id:
                MANIFESTATION.transform(("dataset", "deleted"), True)},
        )
        desired = Deployment(nodes=[node])
        node_state = NodeState(
            uuid=node.uuid,
            hostname=u"10.1.1.1",
            applications={APPLICATION_WITH_VOLUME},
            devices={}, paths={},
            manifestations={MANIFESTATION.dataset_id: MANIFESTATION})
        current = DeploymentState(nodes=[node_state])

        api = P2PManifestationDeployer(
            u"10.1.1.1", create_volume_service(self), node_uuid=node.uuid,
        )
        changes = api.calculate_changes(desired, current,
                                        NodeLocalState(node_state=node_state))
        self.assertEqual(NO_CHANGES, changes)

    def test_no_resize_if_in_use(self):
        """
        ``P2PManifestationDeployer.calculate_changes`` ensures dataset
        deletion happens only if there is no application using the deleted
        dataset.

        This will eventually be switched to use a lease system, rather
        than inspecting application configuration.
        """
        current_node = NodeState(
            hostname=u"node1.example.com",
            manifestations={MANIFESTATION.dataset_id: MANIFESTATION},
            devices={}, paths={},
            applications={APPLICATION_WITH_VOLUME},
        )
        desired_node = Node(
            hostname=u"node1.example.com",
            manifestations={MANIFESTATION_WITH_SIZE.dataset_id:
                            MANIFESTATION_WITH_SIZE},
        )

        current = DeploymentState(nodes=[current_node])
        desired = Deployment(nodes=[desired_node])
        api = P2PManifestationDeployer(current_node.hostname,
                                       create_volume_service(self))

        changes = api.calculate_changes(
            desired, current, NodeLocalState(node_state=current_node))

        expected = NO_CHANGES
        self.assertEqual(expected, changes)

    def test_no_handoff_if_in_use(self):
        """
        ``P2PManifestationDeployer.calculate_changes`` ensures dataset handoff
        happens only if there is no application using the dataset that
        needs to be moved.

        This will eventually be switched to use a lease system, rather
        than inspecting application configuration.
        """
        node_state = NodeState(
            hostname=u"node1.example.com",
            manifestations={MANIFESTATION.dataset_id:
                            MANIFESTATION},
            paths={}, devices={},
            applications={APPLICATION_WITH_VOLUME},
        )
        another_node_state = NodeState(
            hostname=u"node2.example.com", manifestations={},
            devices={}, paths={},
        )
        current = DeploymentState(nodes=[node_state, another_node_state])
        desired = Deployment(nodes={
            Node(hostname=node_state.hostname),
            Node(hostname=another_node_state.hostname,
                 manifestations={MANIFESTATION.dataset_id:
                                 MANIFESTATION}),
        })

        api = P2PManifestationDeployer(
            node_state.hostname, create_volume_service(self),
        )

        changes = api.calculate_changes(desired, current,
                                        NodeLocalState(node_state=node_state))
        self.assertEqual(NO_CHANGES, changes)

    def test_no_handoff_if_destination_unknown(self):
        """
        If there is no known state for the destination of a handoff, then no
        handoff is suggested by ``calculate_changes``.
        """
        node_state = NodeState(
            uuid=uuid4(),
            hostname=u"192.2.0.1",
            manifestations={MANIFESTATION.dataset_id:
                            MANIFESTATION},
            devices={}, paths={},
        )
        current = DeploymentState(nodes=[node_state])
        desired = Deployment(nodes={
            Node(uuid=uuid4(),
                 manifestations={MANIFESTATION.dataset_id:
                                 MANIFESTATION}),
        })

        api = P2PManifestationDeployer(
            node_state.hostname, create_volume_service(self),
            node_uuid=node_state.uuid,
        )

        changes = api.calculate_changes(desired, current,
                                        NodeLocalState(node_state=node_state))
        self.assertEqual(NO_CHANGES, changes)

    def test_volume_handoff(self):
        """
        ``P2PManifestationDeployer.calculate_changes`` specifies that a volume
        was previously running on this node but is now running on another
        node must be handed off.
        """
        node_state = NodeState(
            hostname=u"node1.example.com",
            manifestations={MANIFESTATION.dataset_id:
                            MANIFESTATION},
            devices={}, paths={},
            applications=[],
        )
        another_node_state = NodeState(
            hostname=u"node2.example.com",
            manifestations={}, devices={}, paths={},
        )
        current = DeploymentState(nodes=[node_state, another_node_state])
        desired = Deployment(nodes={
            Node(hostname=node_state.hostname),
            Node(hostname=another_node_state.hostname,
                 manifestations={MANIFESTATION.dataset_id:
                                 MANIFESTATION}),
        })

        api = P2PManifestationDeployer(
            node_state.hostname, create_volume_service(self),
        )

        changes = api.calculate_changes(desired, current,
                                        NodeLocalState(node_state=node_state))
        volume = APPLICATION_WITH_VOLUME.volume

        expected = sequentially(changes=[
            in_parallel(changes=[HandoffDataset(
                dataset=volume.dataset,
                hostname=another_node_state.hostname)]),
        ])
        self.assertEqual(expected, changes)

    def test_no_volume_changes(self):
        """
        ``P2PManifestationDeployer.calculate_changes`` specifies no work for
        the volume if it was and is supposed to be available on the node.
        """
        current_node = NodeState(
            hostname=u"node1.example.com",
            applications=frozenset({APPLICATION_WITH_VOLUME}),
            manifestations={MANIFESTATION.dataset_id:
                            MANIFESTATION},
            devices={}, paths={},
        )
        desired_node = Node(
            hostname=u"node1.example.com",
            applications=frozenset({APPLICATION_WITH_VOLUME}),
            manifestations={MANIFESTATION.dataset_id:
                            MANIFESTATION},
        )
        current = DeploymentState(nodes=[current_node])
        desired = Deployment(nodes=[desired_node])

        api = P2PManifestationDeployer(
            current_node.hostname, create_volume_service(self),
        )

        changes = api.calculate_changes(
            desired, current, NodeLocalState(node_state=current_node))
        expected = NO_CHANGES
        self.assertEqual(expected, changes)

    def test_metadata_does_not_cause_changes(self):
        """
        ``P2PManifestationDeployer.calculate_changes`` indicates no
        action necessary if the configuration has metadata for a dataset
        that is a volume.

        Current cluster state lacks metadata, so we want to verify no
        erroneous restarts are suggested.
        """
        node_state = NodeState(
            hostname=u"node1.example.com",
            applications={APPLICATION_WITH_VOLUME},
            manifestations={MANIFESTATION.dataset_id: MANIFESTATION},
            devices={}, paths={},
        )
        current_nodes = [node_state]
        manifestation_with_metadata = MANIFESTATION.transform(
            ["dataset", "metadata"], {u"xyz": u"u"})

        desired_nodes = [
            Node(
                hostname=u"node1.example.com",
                applications={APPLICATION_WITH_VOLUME.transform(
                    ["volume", "manifestation"], manifestation_with_metadata)},
                manifestations={MANIFESTATION.dataset_id:
                                manifestation_with_metadata},
            ),
        ]

        # The discovered current configuration of the cluster reveals the
        # application is running here.
        current = DeploymentState(nodes=current_nodes)
        desired = Deployment(nodes=desired_nodes)

        api = P2PManifestationDeployer(
            u"node1.example.com",
            create_volume_service(self),
        )

        changes = api.calculate_changes(desired, current,
                                        NodeLocalState(node_state=node_state))
        self.assertEqual(changes, NO_CHANGES)

    def test_dataset_created(self):
        """
        ``P2PManifestationDeployer.calculate_changes`` specifies that a
        new dataset must be created if the desired configuration specifies
        that a dataset that previously existed nowhere is going to be on
        this node.
        """
        hostname = u"node1.example.com"

        node_state = NodeState(hostname=hostname, applications=[],
                               manifestations={}, devices={}, paths={})
        current = DeploymentState(nodes=frozenset({node_state}))

        api = P2PManifestationDeployer(
            hostname,
            create_volume_service(self),
        )

        node = Node(
            hostname=hostname,
            manifestations={MANIFESTATION.dataset_id: MANIFESTATION},
        )
        desired = Deployment(nodes=frozenset({node}))

        changes = api.calculate_changes(desired, current,
                                        NodeLocalState(node_state=node_state))

        expected = sequentially(changes=[
            in_parallel(changes=[CreateDataset(
                dataset=MANIFESTATION.dataset)])])
        self.assertEqual(expected, changes)

    def test_ignore_deleted(self):
        """
        ``P2PManifestationDeployer.calculate_changes`` ignores configured but
        deleted datasets when calculating changes.
        """
        hostname = u"node1.example.com"

        node_state = NodeState(hostname=hostname, applications=[],
                               manifestations={}, devices={}, paths={})
        current = DeploymentState(nodes=frozenset({node_state}))

        api = P2PManifestationDeployer(
            hostname,
            create_volume_service(self),
        )

        node = Node(
            hostname=hostname,
            manifestations={
                MANIFESTATION.dataset_id: MANIFESTATION.transform(
                    ['dataset', 'deleted'], True
                )
            },
        )
        desired = Deployment(nodes=frozenset({node}))

        changes = api.calculate_changes(desired, current,
                                        NodeLocalState(node_state=node_state))

        self.assertEqual(NO_CHANGES, changes)

    def test_dataset_resize(self):
        """
        ``P2PManifestationDeployer.calculate_changes`` specifies that a
        dataset will be resized if a dataset which was previously hosted
        on this node continues to be on this node but specifies a dataset
        maximum_size that differs to the existing dataset size.
        """
        current_node = NodeState(
            hostname=u"node1.example.com",
            manifestations={MANIFESTATION.dataset_id: MANIFESTATION},
            paths={}, devices={},
            applications=[],
        )
        desired_node = Node(
            hostname=u"node1.example.com",
            manifestations={MANIFESTATION_WITH_SIZE.dataset_id:
                            MANIFESTATION_WITH_SIZE},
            applications=[],
        )

        current = DeploymentState(nodes=[current_node])
        desired = Deployment(nodes=frozenset([desired_node]))

        api = P2PManifestationDeployer(
            current_node.hostname,
            create_volume_service(self),
        )

        changes = api.calculate_changes(
            desired, current, NodeLocalState(node_state=current_node))

        expected = sequentially(changes=[
            in_parallel(
                changes=[ResizeDataset(
                    dataset=APPLICATION_WITH_VOLUME_SIZE.volume.dataset,
                    )]
            )
        ])
        self.assertEqual(expected, changes)

    def test_dataset_resized_before_move(self):
        """
        ``P2PManifestationDeployer.calculate_changes`` specifies that a
        dataset will be resized if it is to be relocated to a different
        node but specifies a maximum_size that differs to the existing
        size. The dataset will be resized before moving.
        """
        node_state = NodeState(
            hostname=u"node1.example.com",
            manifestations={MANIFESTATION.dataset_id: MANIFESTATION},
            devices={}, paths={}, applications=[]
        )
        current_nodes = [
            node_state,
            NodeState(
                hostname=u"node2.example.com",
                manifestations={}, devices={}, paths={},
                applications=[],
            )
        ]
        desired_nodes = [
            Node(
                hostname=u"node1.example.com",
            ),
            Node(
                hostname=u"node2.example.com",
                manifestations={MANIFESTATION_WITH_SIZE.dataset_id:
                                MANIFESTATION_WITH_SIZE},
            ),
        ]

        current = DeploymentState(nodes=current_nodes)
        desired = Deployment(nodes=desired_nodes)

        api = P2PManifestationDeployer(
            u"node1.example.com", create_volume_service(self),
        )

        changes = api.calculate_changes(desired, current,
                                        NodeLocalState(node_state=node_state))

        dataset = MANIFESTATION_WITH_SIZE.dataset

        # expected is: resize, push, handoff
        expected = sequentially(changes=[
            in_parallel(
                changes=[ResizeDataset(dataset=dataset)],
            ),
            in_parallel(
                changes=[HandoffDataset(
                    dataset=dataset,
                    hostname=u'node2.example.com')]
            )])
        self.assertEqual(expected, changes)

    def test_different_node_is_ignorant(self):
        """
        The fact that a different node is ignorant about its manifestations
        does not prevent calculating changes necessary for the current
        node.
        """
        node_state = NodeState(
            hostname=u"10.1.1.1",
            uuid=uuid4(),
            manifestations={MANIFESTATION.dataset_id:
                            MANIFESTATION},
            devices={}, paths={},
            applications=[],
        )
        another_node_state = NodeState(hostname=u"10.1.2.3", uuid=uuid4())

        api = P2PManifestationDeployer(node_state.hostname,
                                       create_volume_service(self),
                                       node_uuid=node_state.uuid)
        current = DeploymentState(nodes=[node_state, another_node_state])
        desired = Deployment(nodes=[
            Node(hostname=api.hostname, uuid=api.node_uuid,
                 manifestations=node_state.manifestations.transform(
                     (DATASET_ID, "dataset", "deleted"), True))])

        changes = api.calculate_changes(
            desired, current, NodeLocalState(node_state=node_state))
        expected = sequentially(changes=[
            in_parallel(changes=[DeleteDataset(dataset=DATASET.set(
                "deleted", True))])
            ])
        self.assertEqual(expected, changes)


class CreateDatasetTests(TestCase):
    """
    Tests for ``CreateDataset``.
    """
    def test_creates(self):
        """
        ``CreateDataset.run()`` creates the named volume.
        """
        volume_service = create_volume_service(self)
        deployer = P2PManifestationDeployer(
            u'example.com', volume_service)
        volume = APPLICATION_WITH_VOLUME.volume
        create = CreateDataset(dataset=volume.dataset)
        create.run(
            deployer, state_persister=InMemoryStatePersister())
        self.assertIn(
            volume_service.get(_to_volume_name(volume.dataset.dataset_id)),
            list(self.successResultOf(volume_service.enumerate())))

    def test_creates_respecting_size(self):
        """
        ``CreateDataset.run()`` creates the named volume with a ``VolumeSize``
        instance respecting the maximum_size passed in from the
        ``AttachedVolume``.
        """
        EXPECTED_SIZE_BYTES = 1024 * 1024 * 100
        EXPECTED_SIZE = VolumeSize(maximum_size=EXPECTED_SIZE_BYTES)

        volume_service = create_volume_service(self)
        deployer = P2PManifestationDeployer(
            u'example.com', volume_service)
        volume = APPLICATION_WITH_VOLUME_SIZE.volume
        create = CreateDataset(dataset=volume.dataset)
        create.run(
            deployer, state_persister=InMemoryStatePersister())
        enumerated_volumes = list(
            self.successResultOf(volume_service.enumerate())
        )
        expected_volume = volume_service.get(
            _to_volume_name(volume.dataset.dataset_id), size=EXPECTED_SIZE
        )
        self.assertIn(expected_volume, enumerated_volumes)
        self.assertEqual(expected_volume.size, EXPECTED_SIZE)

    def test_return(self):
        """
        ``CreateDataset.run()`` returns a ``Deferred`` that fires with the
        created volume.
        """
        deployer = P2PManifestationDeployer(
            u'example.com', create_volume_service(self))
        volume = APPLICATION_WITH_VOLUME.volume
        create = CreateDataset(dataset=volume.dataset)
        result = self.successResultOf(create.run(
            deployer, state_persister=InMemoryStatePersister()))
        self.assertEqual(result, deployer.volume_service.get(
            _to_volume_name(volume.dataset.dataset_id)))


class DeleteDatasetTests(TestCase):
    """
    Tests for ``DeleteDataset``.
    """
    def setUp(self):
        super(DeleteDatasetTests, self).setUp()
        self.volume_service = create_volume_service(self)
        self.deployer = P2PManifestationDeployer(
            u'example.com', self.volume_service)

        id1 = unicode(uuid4())
        self.volume1 = self.volume_service.get(_to_volume_name(id1))
        id2 = unicode(uuid4())
        self.volume2 = self.volume_service.get(_to_volume_name(id2))
        self.successResultOf(self.volume_service.create(self.volume1))
        self.successResultOf(self.volume_service.create(self.volume2))

    def test_deletes(self):
        """
        ``DeleteDataset.run()`` deletes volumes whose ``dataset_id`` matches
        the one the instance was created with.
        """
        delete = DeleteDataset(
            dataset=Dataset(dataset_id=self.volume2.name.dataset_id))
        self.successResultOf(delete.run(
            self.deployer, state_persister=InMemoryStatePersister()))

        self.assertEqual(
            list(self.successResultOf(self.volume_service.enumerate())),
            [self.volume1])

    @validate_logging(
        lambda test, logger: logger.flush_tracebacks(CustomException))
    def test_failed_create(self, logger):
        """
        Failed deletions of volumes does not result in a failed result from
        ``DeleteDataset.run()``.

        The traceback is, however, logged.
        """
        self.patch(self.volume_service.pool, "destroy",
                   lambda fs: fail(CustomException()))
        self.patch(_p2p, "_logger", logger)
        delete = DeleteDataset(
            dataset=Dataset(dataset_id=self.volume2.name.dataset_id))
        self.successResultOf(delete.run(
            self.deployer, state_persister=InMemoryStatePersister()))


class ResizeVolumeTests(AsyncTestCase):
    """
    Tests for ``ResizeVolume``.
    """
    def test_sets_size(self):
        """
        ``ResizeVolume.run`` changes the maximum size of the named volume.
        """
        size = VolumeSize(maximum_size=1234567890)
        volume_service = create_volume_service(self)
        volume_name = VolumeName(namespace=u"default", dataset_id=u"myvol")
        volume = volume_service.get(volume_name)
        d = volume_service.create(volume)

        def created(ignored):
            dataset = Dataset(
                dataset_id=volume_name.dataset_id,
                maximum_size=size.maximum_size,
            )
            change = ResizeDataset(dataset=dataset)
            deployer = P2PManifestationDeployer(
                u'example.com', volume_service)
            return change.run(
                deployer, state_persister=InMemoryStatePersister())
        d.addCallback(created)

        def resized(ignored):
            # enumerate re-loads size data from the system
            # get does not.
            # so use enumerate.
            return volume_service.pool.enumerate()
        d.addCallback(resized)

        def got_filesystems(filesystems):
            (filesystem,) = filesystems
            self.assertEqual(size, filesystem.size)
        d.addCallback(got_filesystems)
        return d


class HandoffVolumeTests(TestCase):
    """
    Tests for ``HandoffVolume``.
    """
    def test_handoff(self):
        """
        ``HandoffVolume.run()`` hands off the named volume to the given
        destination nodex.
        """
        volume_service = create_volume_service(self)
        hostname = b"dest.example.com"

        result = []

        def _handoff(volume, destination):
            result.extend([volume, destination])
        self.patch(volume_service, "handoff", _handoff)
        deployer = P2PManifestationDeployer(
            u'example.com', volume_service)
        handoff = HandoffDataset(
            dataset=APPLICATION_WITH_VOLUME.volume.dataset,
            hostname=hostname)
        handoff.run(
            deployer, state_persister=InMemoryStatePersister())
        self.assertEqual(
            result,
            [volume_service.get(_to_volume_name(DATASET.dataset_id)),
             RemoteVolumeManager(standard_node(hostname))])

    def test_return(self):
        """
        ``HandoffVolume.run()`` returns the result of
        ``VolumeService.handoff``.
        """
        result = Deferred()
        volume_service = create_volume_service(self)
        self.patch(volume_service, "handoff",
                   lambda volume, destination: result)
        deployer = P2PManifestationDeployer(
            u'example.com', volume_service)
        handoff = HandoffDataset(
            dataset=APPLICATION_WITH_VOLUME.volume.dataset,
            hostname=b"dest.example.com")
        handoff_result = handoff.run(
            deployer, state_persister=InMemoryStatePersister())
        self.assertIs(handoff_result, result)


class PushVolumeTests(TestCase):
    """
    Tests for ``PushVolume``.
    """
    def test_push(self):
        """
        ``PushVolume.run()`` pushes the named volume to the given destination
        node.
        """
        volume_service = create_volume_service(self)
        hostname = b"dest.example.com"

        result = []

        def _push(volume, destination):
            result.extend([volume, destination])
        self.patch(volume_service, "push", _push)
        deployer = P2PManifestationDeployer(
            u'example.com', volume_service)
        push = PushDataset(
            dataset=APPLICATION_WITH_VOLUME.volume.dataset,
            hostname=hostname)
        push.run(
            deployer, state_persister=InMemoryStatePersister())
        self.assertEqual(
            result,
            [volume_service.get(_to_volume_name(DATASET.dataset_id)),
             RemoteVolumeManager(standard_node(hostname))])

    def test_return(self):
        """
        ``PushVolume.run()`` returns the result of
        ``VolumeService.push``.
        """
        result = Deferred()
        volume_service = create_volume_service(self)
        self.patch(volume_service, "push",
                   lambda volume, destination: result)
        deployer = P2PManifestationDeployer(
            u'example.com', volume_service)
        push = PushDataset(
            dataset=APPLICATION_WITH_VOLUME.volume.dataset,
            hostname=b"dest.example.com")
        push_result = push.run(
            deployer, state_persister=InMemoryStatePersister())
        self.assertIs(push_result, result)
