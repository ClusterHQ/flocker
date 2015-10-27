# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for the Flocker REST API client.
"""

from uuid import uuid4

from bitmath import GiB

from ipaddr import IPAddress

from zope.interface.verify import verifyObject

from pyrsistent import pmap

from eliot import ActionType
from eliot.testing import capture_logging, assertHasAction, LoggedAction

from twisted.trial.unittest import TestCase
from twisted.python.filepath import FilePath
from twisted.internet.task import Clock
from twisted.internet import reactor
from twisted.internet.endpoints import TCP4ServerEndpoint
from twisted.web.http import BAD_REQUEST
from twisted.internet.defer import gatherResults

from .._client import (
    IFlockerAPIV1Client, FakeFlockerClient, Dataset, DatasetAlreadyExists,
    DatasetState, FlockerClient, ResponseError, _LOG_HTTP_REQUEST,
    Lease, LeaseAlreadyHeld, Node,
)
from ...ca import rest_api_context_factory
from ...ca.testtools import get_credential_sets
from ...testtools import find_free_port
from ...control._persistence import ConfigurationPersistenceService
from ...control._clusterstate import ClusterStateService
from ...control.httpapi import create_api_service
from ...control import (
    NodeState, NonManifestDatasets, Dataset as ModelDataset, ChangeSource,
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

    The ``TestCase`` should have two 0-argument methods:

    create_client: Returns a ``IFlockerAPIV1Client`` provider.
    synchronize_state: Make state match the configuration.
    """
    class InterfaceTests(TestCase):
        def setUp(self):
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

        def assert_creates(self, client, dataset_id=None, maximum_size=None,
                           **create_kwargs):
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

        def test_list_state(self):
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
            d.addCallback(
                self.assertItemsEqual,
                [
                    Lease(
                        dataset_id=d1, node_uuid=self.node_1.uuid, expires=10
                    ),
                    Lease(
                        dataset_id=d3, node_uuid=self.node_2.uuid, expires=10.5
                    )
                ]
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

        def test_list_nodes(self):
            """
            ``list_nodes`` returns a ``Deferred`` firing with a ``list`` of
            ``Node``s.
            """
            d = self.client.list_nodes()
            d.addCallback(
                self.assertItemsEqual,
                [self.node_1, self.node_2]
            )
            return d

    return InterfaceTests


class FakeFlockerClientTests(make_clientv1_tests()):
    """
    Interface tests for ``FakeFlockerClient``.
    """
    def create_client(self):
        return FakeFlockerClient(
            nodes=[self.node_1, self.node_2]
        )

    def synchronize_state(self):
        return self.client.synchronize_state()


class FlockerClientTests(make_clientv1_tests()):
    """
    Interface tests for ``FlockerClient``.
    """
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
        self.cluster_state_service.apply_changes_from_source(
            source=source,
            changes=[
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
        node_states = [NodeState(uuid=node.uuid, hostname=unicode(node.uuid),
                                 manifestations=node.manifestations,
                                 paths={manifestation.dataset_id:
                                        FilePath(b"/flocker").child(bytes(
                                            manifestation.dataset_id))
                                        for manifestation
                                        in node.manifestations.values()},
                                 devices={})
                       for node in deployment.nodes]
        self.cluster_state_service.apply_changes(node_states)

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
