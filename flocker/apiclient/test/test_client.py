# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for the Flocker REST API client.
"""

from uuid import uuid4, UUID
from unittest import skipUnless
from subprocess import check_output

from bitmath import GiB

from ipaddr import IPAddress

from zope.interface.verify import verifyObject

from pyrsistent import pmap

from eliot import ActionType
from eliot.testing import capture_logging, assertHasAction, LoggedAction

from twisted.python.filepath import FilePath
from twisted.internet.task import Clock
from twisted.internet import reactor
from twisted.internet.endpoints import TCP4ServerEndpoint
from twisted.web.http import BAD_REQUEST
from twisted.internet.defer import gatherResults
from twisted.python.runtime import platform
from twisted.python.procutils import which

from .._client import (
    IFlockerAPIV1Client, FakeFlockerClient, Dataset, DatasetAlreadyExists,
    DatasetState, FlockerClient, ResponseError, _LOG_HTTP_REQUEST,
    Lease, LeaseAlreadyHeld, Node, Container, ContainerAlreadyExists,
    DatasetsConfiguration, ConfigurationChanged, conditional_create,
    _LOG_CONDITIONAL_CREATE, ContainerState, MountedDataset,
)
from ...ca import rest_api_context_factory
from ...ca.testtools import get_credential_sets
from ...testtools import (
    find_free_port, random_name, CustomException, AsyncTestCase, TestCase,
)
from ...control._persistence import ConfigurationPersistenceService
from ...control._clusterstate import ClusterStateService
from ...control.httpapi import create_api_service
from ...control import (
    NodeState, NonManifestDatasets, Dataset as ModelDataset, ChangeSource,
    DockerImage, UpdateNodeStateEra,
)
from ...restapi._logging import JSON_REQUEST
from ...restapi import _infrastructure as rest_api
from ... import __version__

DATASET_SIZE = int(GiB(1).to_Byte().value)


def make_clientv1_tests():
    """
    Create a ``TestCase`` for testing ``IFlockerAPIV1Client``.

    The presumption is that the state of datasets is completely under
    control of this process. So when testing a real client it will be
    talking to a in-process server.

    The ``TestCase`` should have three 0-argument methods:

    create_client: Returns a ``IFlockerAPIV1Client`` provider.
    synchronize_state: Make state match the configuration.
    get_configuration_tag: Return the configuration hash.
    """
    class InterfaceTests(AsyncTestCase):
        def setUp(self):
            super(InterfaceTests, self).setUp()
            self.node_1 = Node(
                uuid=uuid4(),
                public_address=IPAddress('10.0.0.1')
            )
            self.node_2 = Node(
                uuid=uuid4(),
                public_address=IPAddress('10.0.0.2')
            )
            self.client = self.create_client()

        def test_interface(self):
            """
            The created client provides ``IFlockerAPIV1Client``.
            """
            self.assertTrue(verifyObject(IFlockerAPIV1Client, self.client))

        def test_list_dataset_configuration(self):
            """
            The listed configuration includes the hashed tag of the
            configuration and a mapping of configured datasets.
            """
            creating = self.client.create_dataset(primary=self.node_1.uuid)

            def created(dataset):
                d = self.client.list_datasets_configuration()
                d.addCallback(self.assertEqual,
                              DatasetsConfiguration(
                                  tag=self.get_configuration_tag(),
                                  datasets={dataset.dataset_id: dataset}))
                return d
            creating.addCallback(created)
            return creating

        def assert_creates(self, client, dataset_id=None, maximum_size=None,
                           configuration_tag=None, **create_kwargs):
            """
            Create a dataset and ensure it shows up in the configuration and
            return result of the ``create_dataset`` call.

            :param IFlockerAPIV1Client client: Client to use.
            :param dataset_id: Dataset ID to use, or ``None`` if it should
                be generated.
            :param maximum_size: Maximum size to use, or ``None`` if not set.
            :param create_kwargs: Additional arguments to pass to
                ``create_dataset``.

            :return: ``Deferred`` firing with result of
                ``create_dataset``.
            """
            created = client.create_dataset(
                dataset_id=dataset_id, maximum_size=maximum_size,
                configuration_tag=configuration_tag,
                **create_kwargs)

            def got_result(dataset):
                if dataset_id is None:
                    expected_dataset_id = dataset.dataset_id
                else:
                    expected_dataset_id = dataset_id
                expected = Dataset(dataset_id=expected_dataset_id,
                                   maximum_size=maximum_size,
                                   **create_kwargs)
                self.assertEqual(expected, dataset)

                listed = client.list_datasets_configuration()
                listed.addCallback(
                    lambda result: self.assertIn(expected, result))
                listed.addCallback(lambda _: dataset)
                return listed

            created.addCallback(got_result)
            return created

        def test_create_assigns_dataset(self):
            """
            If no ``dataset_id`` is specified when calling ``create_dataset``,
            a new one is generated.
            """
            return self.assert_creates(self.client,
                                       primary=self.node_1.uuid,
                                       maximum_size=DATASET_SIZE)

        def test_create_no_size(self):
            """
            If no ``maximum_size`` is specified when calling ``create_dataset``
            the result has no size set.
            """
            return self.assert_creates(self.client, primary=self.node_1.uuid)

        def test_create_given_dataset(self):
            """
            If a ``dataset_id`` is specified when calling ``create_dataset``,
            it is used as the ID for the resulting created dataset.
            """
            dataset_id = uuid4()
            d = self.assert_creates(self.client, primary=self.node_1.uuid,
                                    maximum_size=DATASET_SIZE,
                                    dataset_id=dataset_id)
            d.addCallback(lambda dataset: self.assertEqual(dataset.dataset_id,
                                                           dataset_id))
            return d

        def test_create_with_metadata(self):
            """
            The metadata passed to ``create_dataset`` is stored with the
            dataset.
            """
            d = self.assert_creates(self.client, primary=self.node_1.uuid,
                                    maximum_size=DATASET_SIZE,
                                    metadata={u"hello": u"there"})
            d.addCallback(lambda dataset: self.assertEqual(
                dataset.metadata, pmap({u"hello": u"there"})))
            return d

        def test_create_conflicting_dataset_id(self):
            """
            Creating two datasets with same ``dataset_id`` results in an
            ``DatasetAlreadyExists``.
            """
            d = self.assert_creates(self.client, primary=self.node_1.uuid,
                                    maximum_size=DATASET_SIZE)

            def got_result(dataset):
                d = self.client.create_dataset(primary=self.node_1.uuid,
                                               maximum_size=DATASET_SIZE,
                                               dataset_id=dataset.dataset_id)
                return self.assertFailure(d, DatasetAlreadyExists)
            d.addCallback(got_result)
            return d

        def test_create_matching_tag(self):
            """
            If a matching tag is given the create succeeds.
            """
            return self.assert_creates(
                self.client, primary=self.node_1.uuid,
                configuration_tag=self.get_configuration_tag())

        def test_create_conflicting_tag(self):
            """
            If a conflicting tag is given then an appropriate exception is
            raised.
            """
            d = self.client.create_dataset(primary=self.node_1.uuid,
                                           configuration_tag=u"willnotmatch")
            return self.assertFailure(d, ConfigurationChanged)

        def test_delete_returns_dataset(self):
            """
            ``delete_dataset`` returns a deferred that fires with the
            ``Dataset`` that has been deleted.
            """
            dataset_id = uuid4()

            d = self.assert_creates(self.client, primary=self.node_1.uuid,
                                    maximum_size=DATASET_SIZE,
                                    dataset_id=dataset_id)
            d.addCallback(
                lambda _: self.client.delete_dataset(dataset_id))

            def got_result(dataset):
                expected_removed = Dataset(
                    dataset_id=dataset_id, primary=self.node_1.uuid,
                    maximum_size=DATASET_SIZE
                )
                self.assertEqual(expected_removed, dataset)

            d.addCallback(got_result)
            return d

        def test_deleted_not_listed(self):
            """
            ``list_datasets_configuration`` does not list deleted datasets.
            """
            dataset_id = uuid4()

            d = self.assert_creates(self.client, primary=self.node_1.uuid,
                                    maximum_size=DATASET_SIZE,
                                    dataset_id=dataset_id)
            d.addCallback(
                lambda _: self.client.delete_dataset(dataset_id))

            def got_result(_):
                listed = self.client.list_datasets_configuration()
                return listed

            d.addCallback(got_result)

            def not_listed(listed_datasets):
                expected_removed = Dataset(
                    dataset_id=dataset_id, primary=self.node_1.uuid,
                    maximum_size=DATASET_SIZE
                )
                self.assertNotIn(expected_removed, listed_datasets)

            d.addCallback(not_listed)
            return d

        def test_delete_matching_tag(self):
            """
            If a matching tag is given the delete succeeds.
            """
            d = self.assert_creates(self.client, primary=self.node_1.uuid)
            d.addCallback(
                lambda dataset: self.client.delete_dataset(
                    dataset.dataset_id,
                    configuration_tag=self.get_configuration_tag()))
            d.addCallback(lambda _: self.client.list_datasets_configuration())
            d.addCallback(lambda result: self.assertFalse(result.datasets))
            return d

        def test_delete_conflicting_tag(self):
            """
            If a conflicting tag is given then an appropriate exception is
            raised.
            """
            d = self.client.delete_dataset(dataset_id=uuid4(),
                                           configuration_tag=u"willnotmatch")
            return self.assertFailure(d, ConfigurationChanged)

        def test_move(self):
            """
            ``move_dataset`` changes the dataset's primary.
            """
            dataset_id = uuid4()

            d = self.assert_creates(self.client, primary=self.node_1.uuid,
                                    maximum_size=DATASET_SIZE,
                                    dataset_id=dataset_id)
            d.addCallback(
                lambda _: self.client.move_dataset(
                    self.node_2.uuid, dataset_id
                )
            )

            def got_result(dataset):
                listed = self.client.list_datasets_configuration()
                listed.addCallback(lambda l: (dataset, l))
                return listed
            d.addCallback(got_result)

            def got_listing(result):
                moved_result, listed_datasets = result
                expected = Dataset(dataset_id=dataset_id,
                                   primary=self.node_2.uuid,
                                   maximum_size=DATASET_SIZE)
                self.assertEqual((expected, expected in listed_datasets),
                                 (moved_result, True))
            d.addCallback(got_listing)
            return d

        def test_move_matching_tag(self):
            """
            If a matching tag is given the move succeeds.
            """
            d = self.assert_creates(self.client, primary=self.node_1.uuid)
            d.addCallback(
                lambda dataset: self.client.move_dataset(
                    dataset_id=dataset.dataset_id,
                    primary=self.node_2.uuid,
                    configuration_tag=self.get_configuration_tag()))
            d.addCallback(lambda _: self.client.list_datasets_configuration())
            d.addCallback(lambda result: self.assertEqual(
                set(d.primary for d in result), {self.node_2.uuid}))
            return d

        def test_move_conflicting_tag(self):
            """
            If a conflicting tag is given then an appropriate exception is
            raised.
            """
            d = self.client.move_dataset(primary=self.node_1.uuid,
                                         dataset_id=uuid4(),
                                         configuration_tag=u"willnotmatch")
            return self.assertFailure(d, ConfigurationChanged)

        def test_dataset_state(self):
            """
            ``list_datasets_state`` returns information about state.
            """
            dataset_id = uuid4()
            expected_path = FilePath(b"/flocker/{}".format(dataset_id))
            d = self.assert_creates(self.client, primary=self.node_1.uuid,
                                    maximum_size=DATASET_SIZE * 2,
                                    dataset_id=dataset_id)
            d.addCallback(lambda _: self.synchronize_state())
            d.addCallback(lambda _: self.client.list_datasets_state())
            d.addCallback(lambda states:
                          self.assertIn(
                              DatasetState(dataset_id=dataset_id,
                                           primary=self.node_1.uuid,
                                           maximum_size=DATASET_SIZE * 2,
                                           path=expected_path),
                              states))
            return d

        def test_acquire_lease_result(self):
            """
            ``acquire_lease`` returns a ``Deferred`` firing with ``Lease``
            instance.
            """
            dataset_id = uuid4()
            d = self.client.acquire_lease(dataset_id, self.node_1.uuid, 123)
            d.addCallback(self.assertEqual, Lease(dataset_id=dataset_id,
                                                  node_uuid=self.node_1.uuid,
                                                  expires=123))
            return d

        def test_release_lease_result(self):
            """
            ``release_lease`` returns a ``Deferred`` firing with ``Lease``
            instance.
            """
            dataset_id = uuid4()
            d = self.client.acquire_lease(dataset_id, self.node_1.uuid, 123)
            d.addCallback(lambda _: self.client.release_lease(dataset_id))
            d.addCallback(self.assertEqual, Lease(dataset_id=dataset_id,
                                                  node_uuid=self.node_1.uuid,
                                                  expires=123))
            return d

        def test_list_leases(self):
            """
            ``list_leases`` lists acquired leases that have not been released
            yet.
            """
            d1, d2, d3 = uuid4(), uuid4(), uuid4()
            d = gatherResults([
                self.client.acquire_lease(d1, self.node_1.uuid, 10),
                self.client.acquire_lease(d2, self.node_1.uuid, None),
                self.client.acquire_lease(d3, self.node_2.uuid, 10.5),
                ])
            d.addCallback(lambda _: self.client.release_lease(d2))
            d.addCallback(lambda _: self.client.list_leases())
            d.addCallback(frozenset)
            d.addCallback(
                self.assertEqual,
                frozenset([
                    Lease(
                        dataset_id=d1, node_uuid=self.node_1.uuid, expires=10
                    ),
                    Lease(
                        dataset_id=d3, node_uuid=self.node_2.uuid, expires=10.5
                    )
                ])
            )
            return d

        def test_renew_lease(self):
            """
            Acquiring a lease twice on the same dataset and node renews it.
            """
            dataset_id = uuid4()
            d = self.client.acquire_lease(dataset_id, self.node_1.uuid, 123)
            d.addCallback(lambda _: self.client.acquire_lease(
                dataset_id, self.node_1.uuid, 456))
            d.addCallback(self.assertEqual, Lease(dataset_id=dataset_id,
                                                  node_uuid=self.node_1.uuid,
                                                  expires=456))
            return d

        def test_acquire_lease_conflict(self):
            """
            A ``LeaseAlreadyHeld`` exception is raised if an attempt is made to
            acquire a lease that is held by another node.
            """
            dataset_id = uuid4()
            d = self.client.acquire_lease(dataset_id, self.node_1.uuid, 60)
            d.addCallback(lambda _: self.client.acquire_lease(
                dataset_id, self.node_2.uuid, None))
            return self.assertFailure(d, LeaseAlreadyHeld)

        def test_version(self):
            """
            ``version`` returns a ``Deferred`` firing with a ``dict``
            containing ``flocker.__version__``.
            """
            d = self.client.version()
            d.addCallback(
                self.assertEqual,
                {"flocker": __version__},
            )
            return d

        def assert_create_container(self, client):
            expected_container, d = create_container_for_test(
                self, self.client,
            )
            d.addCallback(
                self.assertEqual,
                expected_container,
            )
            d.addCallback(
                lambda ignored: client.list_containers_configuration()
            )
            d.addCallback(
                lambda containers: self.assertIn(
                    expected_container,
                    containers
                )
            )
            return d

        def test_create_container(self):
            """
            ``create_container`` returns a ``Deferred`` firing with the
            configured ``Container``.
            """
            return self.assert_create_container(self.client)

        def test_create_conflicting_container_name(self):
            """
            Creating two containers with same ``name`` results in an
            ``ContainerAlreadyExists``.
            """
            expected_container, d = create_container_for_test(
                self, self.client,
            )

            def got_result(container):
                expected_container, d = create_container_for_test(
                    self, self.client,
                    name=container.name
                )
                return self.assertFailure(d, ContainerAlreadyExists)
            d.addCallback(got_result)
            return d

        def test_container_state(self):
            """
            ``list_containers_state`` returns information about state.
            """
            expected, d = create_container_for_test(self, self.client)

            d.addCallback(lambda _ignored: self.synchronize_state())

            d.addCallback(lambda _ignored: self.client.list_containers_state())

            d.addCallback(
                lambda containers: self.assertIn(
                    ContainerState(
                        node_uuid=expected.node_uuid,
                        name=expected.name,
                        image=expected.image,
                        running=True,
                    ),
                    containers
                )
            )

            return d

        def test_container_volumes(self):
            """
            Mounted datasets are included in response messages.
            """
            d = self.assert_creates(
                self.client, primary=self.node_1.uuid,
                maximum_size=DATASET_SIZE
            )

            def start_container(dataset):
                name = random_name(case=self)
                volumes = [
                    MountedDataset(
                        dataset_id=dataset.dataset_id, mountpoint=u'/data')
                ]
                expected_configuration = Container(
                    node_uuid=self.node_1.uuid,
                    name=name,
                    image=DockerImage.from_string(u'nginx'),
                    volumes=volumes,
                )

                # Create a container with an attached dataset
                d = self.client.create_container(
                    node_uuid=expected_configuration.node_uuid,
                    name=expected_configuration.name,
                    image=expected_configuration.image,
                    volumes=expected_configuration.volumes,
                )

                # Result of create call is stateful container configuration
                d.addCallback(
                    lambda configuration: self.assertEqual(
                        configuration, expected_configuration
                    )
                )

                # Cluster configuration contains stateful container
                d.addCallback(
                    lambda _ignore: self.client.list_containers_configuration()
                ).addCallback(
                    lambda configurations: self.assertIn(
                        expected_configuration, configurations
                    )
                )

                d.addCallback(lambda _ignore: self.synchronize_state())

                expected_state = ContainerState(
                    node_uuid=self.node_1.uuid,
                    name=name,
                    image=DockerImage.from_string(u'nginx'),
                    running=True,
                    volumes=volumes,
                )

                # After convergence, cluster state contains stateful container
                d.addCallback(
                    lambda _ignore: self.client.list_containers_state()
                ).addCallback(
                    lambda states: self.assertIn(expected_state, states)
                )

                return d
            d.addCallback(start_container)

            return d

        def test_delete_container(self):
            """
            ``delete_container`` returns a deferred that fires with ``None``.
            """
            expected_container, d = create_container_for_test(
                self, self.client
            )
            d.addCallback(
                lambda ignored: self.client.delete_container(
                    expected_container.name
                )
            )
            d.addCallback(self.assertIs, None)
            return d

        def test_delete_container_not_listed(self):
            """
            ``list_containers_configuration`` does not list deleted containers.
            """
            expected_container, d = create_container_for_test(
                self, self.client
            )
            d.addCallback(
                lambda ignored: self.client.delete_container(
                    expected_container.name
                )
            )
            d.addCallback(
                lambda ignored: self.client.list_containers_configuration()
            )
            d.addCallback(
                lambda containers: self.assertNotIn(
                    expected_container,
                    containers,
                )
            )
            return d

        def test_list_nodes(self):
            """
            ``list_nodes`` returns a ``Deferred`` firing with a ``list`` of
            ``Node``s.
            """
            d = self.client.list_nodes()
            d.addCallback(frozenset)
            d.addCallback(
                self.assertEqual,
                frozenset([self.node_1, self.node_2]),
            )
            return d

        def test_this_node_uuid(self):
            """
            ``this_node_uuid`` returns ``Deferred`` firing the UUID of the
            current node.
            """
            d = self.client.this_node_uuid()
            d.addCallback(self.assertEqual, self.node_1.uuid)
            return d

    return InterfaceTests


def create_container_for_test(case, client, name=None):
    """
    Use the API client to create a new container for the running test.

    :param TestCase case: The currently running test.
    :param IFlockerClient client: The client for creating containers.
    :param unicode name: The name to be assigned to the container or ``None``
        to assign a random name.

    :return: A two-tuple.  The first element is a ``Container`` describing the
        container which an API call was issued to create.  The second element
        is a ``Deferred`` that fires with the result of the API call.
    """
    if name is None:
        name = random_name(case=case)
    expected_container = Container(
        node_uuid=uuid4(),
        name=name,
        image=DockerImage.from_string(u'nginx'),
    )
    d = client.create_container(
        node_uuid=expected_container.node_uuid,
        name=expected_container.name,
        image=expected_container.image,
    )
    return expected_container, d


class FakeFlockerClientTests(make_clientv1_tests()):
    """
    Interface tests for ``FakeFlockerClient``.
    """
    def create_client(self):
        return FakeFlockerClient(
            nodes=[self.node_1, self.node_2],
            this_node_uuid=self.node_1.uuid,
        )

    def synchronize_state(self):
        return self.client.synchronize_state()

    def get_configuration_tag(self):
        return self.client._configured_datasets


class FlockerClientTests(make_clientv1_tests()):
    """
    Interface tests for ``FlockerClient``.
    """
    @skipUnless(platform.isLinux(),
                "flocker-node-era currently requires Linux.")
    @skipUnless(which("flocker-node-era"),
                "flocker-node-era needs to be in $PATH.")
    def create_client(self):
        """
        Create a new ``FlockerClient`` instance pointing at a running control
        service REST API.

        :return: ``FlockerClient`` instance.
        """
        clock = Clock()
        _, self.port = find_free_port()
        self.persistence_service = ConfigurationPersistenceService(
            clock, FilePath(self.mktemp()))
        self.persistence_service.startService()
        self.cluster_state_service = ClusterStateService(reactor)
        self.cluster_state_service.startService()
        source = ChangeSource()
        # Prevent nodes being deleted by the state wiper.
        source.set_last_activity(reactor.seconds())
        self.era = UUID(check_output(["flocker-node-era"]))
        self.cluster_state_service.apply_changes_from_source(
            source=source,
            changes=[
                UpdateNodeStateEra(era=self.era, uuid=self.node_1.uuid)] + [
                NodeState(uuid=node.uuid, hostname=node.public_address)
                for node in [self.node_1, self.node_2]
            ],
        )
        self.addCleanup(self.cluster_state_service.stopService)
        self.addCleanup(self.persistence_service.stopService)
        credential_set, _ = get_credential_sets()
        credentials_path = FilePath(self.mktemp())
        credentials_path.makedirs()

        api_service = create_api_service(
            self.persistence_service,
            self.cluster_state_service,
            TCP4ServerEndpoint(reactor, self.port, interface=b"127.0.0.1"),
            rest_api_context_factory(
                credential_set.root.credential.certificate,
                credential_set.control),
            # Use consistent fake time for API results:
            clock)
        api_service.startService()
        self.addCleanup(api_service.stopService)

        credential_set.copy_to(credentials_path, user=True)
        return FlockerClient(reactor, b"127.0.0.1", self.port,
                             credentials_path.child(b"cluster.crt"),
                             credentials_path.child(b"user.crt"),
                             credentials_path.child(b"user.key"))

    def synchronize_state(self):
        deployment = self.persistence_service.get()
        # No IP address known, so use UUID for hostname
        node_states = [NodeState(uuid=node.uuid, hostname=unicode(node.uuid),
                                 applications=node.applications,
                                 manifestations=node.manifestations,
                                 paths={manifestation.dataset_id:
                                        FilePath(b"/flocker").child(bytes(
                                            manifestation.dataset_id))
                                        for manifestation
                                        in node.manifestations.values()},
                                 devices={})
                       for node in deployment.nodes]
        self.cluster_state_service.apply_changes(node_states)

    def get_configuration_tag(self):
        return self.persistence_service.configuration_hash()

    @capture_logging(None)
    def test_logging(self, logger):
        """
        Successful HTTP requests are logged.
        """
        dataset_id = uuid4()
        d = self.client.create_dataset(
            primary=self.node_1.uuid, maximum_size=None, dataset_id=dataset_id)
        d.addCallback(lambda _: assertHasAction(
            self, logger, _LOG_HTTP_REQUEST, True, dict(
                url=b"https://127.0.0.1:{}/v1/configuration/datasets".format(
                    self.port),
                method=u"POST",
                request_body=dict(primary=unicode(self.node_1.uuid),
                                  metadata={},
                                  dataset_id=unicode(dataset_id))),
            dict(response_body=dict(primary=unicode(self.node_1.uuid),
                                    metadata={},
                                    deleted=False,
                                    dataset_id=unicode(dataset_id)))))
        return d

    @capture_logging(None)
    def test_cross_process_logging(self, logger):
        """
        Eliot tasks can be traced from the HTTP client to the API server.
        """
        self.patch(rest_api, "_logger", logger)
        my_action = ActionType("my_action", [], [])
        with my_action():
            d = self.client.create_dataset(primary=self.node_1.uuid)

        def got_response(_):
            parent = LoggedAction.ofType(logger.messages, my_action)[0]
            child = LoggedAction.ofType(logger.messages, JSON_REQUEST)[0]
            self.assertIn(child, list(parent.descendants()))
        d.addCallback(got_response)
        return d

    @capture_logging(lambda self, logger: assertHasAction(
        self, logger, _LOG_HTTP_REQUEST, False, dict(
            url=b"https://127.0.0.1:{}/v1/configuration/datasets".format(
                self.port),
            method=u"POST",
            request_body=dict(
                primary=unicode(self.node_1.uuid), maximum_size=u"notint",
                metadata={})),
        {u'exception': u'flocker.apiclient._client.ResponseError'}))
    def test_unexpected_error(self, logger):
        """
        If the ``FlockerClient`` receives an unexpected HTTP response code it
        returns a ``ResponseError`` failure.
        """
        d = self.client.create_dataset(
            primary=self.node_1.uuid, maximum_size=u"notint")
        self.assertFailure(d, ResponseError)
        d.addCallback(lambda exc: self.assertEqual(exc.code, BAD_REQUEST))
        return d

    def test_unset_primary(self):
        """
        If the ``FlockerClient`` receives a dataset state where primary is
        ``None`` it parses it correctly.
        """
        dataset_id = uuid4()
        self.cluster_state_service.apply_changes([
            NonManifestDatasets(datasets={
                unicode(dataset_id): ModelDataset(
                    dataset_id=unicode(dataset_id)),
                })])
        d = self.client.list_datasets_state()
        d.addCallback(lambda states:
                      self.assertEqual(
                          [DatasetState(dataset_id=dataset_id,
                                        primary=None,
                                        maximum_size=None,
                                        path=None)],
                          states))
        return d

    def test_this_node_uuid_retry(self):
        """
        ``this_node_uuid`` retries if the node UUID is unknown.
        """
        # Pretend that the era for node 1 is something else; first try at
        # getting node UUID for real era will therefore fail:
        self.cluster_state_service.apply_changes([
            UpdateNodeStateEra(era=uuid4(), uuid=self.node_1.uuid)])

        # When we lookup the DeploymentState the first time we'll set the
        # value to the correct one, so second try should succeed:
        def as_deployment(original=self.cluster_state_service.as_deployment):
            result = original()
            self.cluster_state_service.apply_changes(changes=[
                UpdateNodeStateEra(era=self.era, uuid=self.node_1.uuid)])
            return result
        self.patch(self.cluster_state_service, "as_deployment", as_deployment)

        d = self.client.this_node_uuid()
        d.addCallback(self.assertEqual, self.node_1.uuid)
        return d

    def test_this_node_uuid_no_retry_on_other_responses(self):
        """
        ``this_node_uuid`` doesn't retry on unexpected responses.
        """
        # Cause 500 errors to be raised by the API endpoint:
        self.patch(self.cluster_state_service, "as_deployment",
                   lambda: 1/0)
        return self.assertFailure(self.client.this_node_uuid(),
                                  ResponseError)


class ConditionalCreateTests(TestCase):
    """
    Tests for ``conditional_create``.
    """
    def setUp(self):
        super(ConditionalCreateTests, self).setUp()
        self.client = FakeFlockerClient()
        self.reactor = Clock()
        self.node_id = uuid4()

    def advance(self):
        """
        Advance the clock such that next step of process happens.
        """
        self.reactor.advance(0.001)

    def unique_key(self, key):
        """
        :return: Condition function that require that the given value for
            ``"key"`` not be present in any dataset's metadata.
        """
        def condition(datasets_config):
            for dataset in datasets_config:
                if dataset.metadata.get("key") == key:
                    raise CustomException()
        return condition

    @capture_logging(assertHasAction, _LOG_CONDITIONAL_CREATE, True)
    def test_simple_success(self, logger):
        """
        If no configuration changes or condition violations occur the creation
        succeeds.
        """
        dataset_id = uuid4()
        d = conditional_create(self.client, self.reactor, lambda config: None,
                               primary=self.node_id, dataset_id=dataset_id)
        self.advance()
        [current_dataset] = self.successResultOf(
            self.client.list_datasets_configuration())
        self.assertEqual([self.successResultOf(d),
                          Dataset(dataset_id=dataset_id,
                                  primary=self.node_id,
                                  maximum_size=None)],
                         [current_dataset, current_dataset])

    def test_immediate_condition_violation(self):
        """
        If a condition violation occurs immediately the creation is aborted
        and the raised exception is returned.
        """
        self.successResultOf(self.client.create_dataset(
            primary=self.node_id, metadata={u"key": u"llave"}))
        self.failureResultOf(
            conditional_create(self.client, self.reactor,
                               self.unique_key(u"llave"),
                               primary=self.node_id),
            CustomException)

    def test_eventual_success(self):
        """
        If the configuration changes between when listing and creation occurs
        the operation is retried until it succeeds.
        """
        d = conditional_create(self.client, self.reactor, lambda config: None,
                               primary=self.node_id)
        # Change configuration in between listing and condition check:
        self.successResultOf(self.client.create_dataset(primary=self.node_id))
        # Creation, which should fail with ConfigurationChanged:
        self.advance()
        # List again:
        self.advance()
        # Create again:
        self.advance()
        self.assertIn(self.successResultOf(d),
                      self.successResultOf(
                          self.client.list_datasets_configuration()))

    def test_eventual_condition_violation(self):
        """
        If a conflict occurs and the condition is violated in a later
        iteration then creation is aborted and the raised exception is
        returned.
        """
        d = conditional_create(self.client, self.reactor,
                               self.unique_key(u"llave"),
                               primary=self.node_id)
        # Change configuration in between listing and condition check:
        self.successResultOf(self.client.create_dataset(primary=self.node_id))
        # Creation, which should fail with ConfigurationChanged:
        self.advance()
        # List again:
        self.advance()
        # Create dataset which will violate the condition:
        self.successResultOf(self.client.create_dataset(
            primary=self.node_id, metadata={u"key": u"llave"}))
        # Create again, which should fail with ConfigurationChanged:
        self.advance()
        # List again, which should fail condition:
        self.advance()
        self.failureResultOf(d, CustomException)

    def test_too_many_retries(self):
        """
        Eventually we give up on retrying if the precondition fails too many
        times.
        """
        d = conditional_create(self.client, self.reactor,
                               lambda config: None,
                               primary=self.node_id)
        # Every time we advance we change the config, invalidating
        # previous result. 2 queries (list+create) for 20 tries, 40th
        # query fails:
        for i in range(39):
            self.assertNoResult(d)
            self.successResultOf(self.client.create_dataset(
                primary=self.node_id))
            self.advance()
        self.failureResultOf(d, ConfigurationChanged)
