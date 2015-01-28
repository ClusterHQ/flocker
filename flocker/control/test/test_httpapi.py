# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
"""
Tests for ``flocker.control.httpapi``.
"""

from io import BytesIO
from uuid import uuid4

from pyrsistent import pmap

from zope.interface.verify import verifyObject

from twisted.internet import reactor
from twisted.internet.defer import gatherResults
from twisted.internet.endpoints import TCP4ServerEndpoint
from twisted.trial.unittest import SynchronousTestCase
from twisted.test.proto_helpers import MemoryReactor
from twisted.web.http import OK, CONFLICT, BAD_REQUEST
from twisted.web.http_headers import Headers
from twisted.web.server import Site
from twisted.web.client import FileBodyProducer, readBody
from twisted.application.service import IService
from twisted.python.filepath import FilePath

from ...restapi.testtools import (
    buildIntegrationTests, dumps, loads, goodResult, badResult)

from .. import Dataset, Manifestation, Node, Deployment
from ..httpapi import DatasetAPIUserV1, create_api_service
from .._persistence import ConfigurationPersistenceService
from ... import __version__


class APITestsMixin(object):
    """
    Helpers for writing integration tests for the Dataset Manager API.
    """
    def initialize(self):
        """
        Create initial objects for the ``DatasetAPIUserV1``.
        """
        self.persistence_service = ConfigurationPersistenceService(
            reactor, FilePath(self.mktemp()))
        self.persistence_service.startService()
        self.addCleanup(self.persistence_service.stopService)

    def assertResponseCode(self, method, path, request_body, expected_code):
        if request_body is None:
            headers = None
            body_producer = None
        else:
            headers = Headers({b"content-type": [b"application/json"]})
            body_producer = FileBodyProducer(BytesIO(dumps(request_body)))

        requesting = self.agent.request(
            method, path, headers, body_producer)

        def check_code(response):
            self.assertEqual(expected_code, response.code)
            return response
        requesting.addCallback(check_code)
        return requesting

    def assertGoodResult(self, method, path, request_body,
                         expected_good_result):
        """
        Assert a particular JSON response for the given API request.

        :param bytes method: HTTP method to request.
        :param bytes path: HTTP path.
        :param unicode expected_good_result: Successful good result we expect.

        :return Deferred: Fires when test is done.
        """
        requesting = self.assertResponseCode(method, path, request_body, OK)
        requesting.addCallback(readBody)
        requesting.addCallback(lambda body: self.assertEqual(
            goodResult(expected_good_result), loads(body)))
        return requesting

    def assertBadResult(self, method, path, request_body,
                        expected_code, expected_bad_result):
        """
        Assert a particular JSON response for the given API request.

        :param bytes method: HTTP method to request.
        :param bytes path: HTTP path.
        :param unicode expected_bad_result: The result expected in the error
            respones.

        :return Deferred: Fires when test is done.
        """
        requesting = self.assertResponseCode(
            method, path, request_body, expected_code)
        requesting.addCallback(readBody)
        requesting.addCallback(lambda body: self.assertEqual(
            badResult(expected_bad_result), loads(body)))
        return requesting


class VersionTestsMixin(APITestsMixin):
    """
    Tests for the service version description endpoint at ``/version``.
    """
    def test_version(self):
        """
        The ``/version`` command returns JSON-encoded ``__version__``.
        """
        return self.assertGoodResult(
            b"GET", b"/version", None, {u'flocker': __version__}
        )


def _build_app(test):
    test.initialize()
    return DatasetAPIUserV1(test.persistence_service).app

RealTestsVersion, MemoryTestsVersion = buildIntegrationTests(
    VersionTestsMixin, "Version", _build_app)


class CreateDatasetTestsMixin(APITestsMixin):
    """
    Tests for the dataset creation endpoint at ``/datasets``.
    """
    # These addresses taken from RFC 5737 (TEST-NET-1)
    NODE_A = b"192.0.2.1"
    NODE_B = b"192.0.2.2"

    def test_wrong_schema(self):
        """
        If a ``POST`` request made to the endpoint includes a body which
        doesn't match the ``definitions/datasets`` schema, the response is an
        error indication a validation failure.
        """
        return self.assertBadResult(
            b"POST", b"/datasets",
            {u"primary": self.NODE_A, u"junk": u"garbage"},
            BAD_REQUEST, {
                u'description':
                    u"The provided JSON doesn't match the required schema.",
                u'errors': [
                    u"Additional properties are not allowed "
                    u"(u'junk' was unexpected)"
                ]
            }
        )

    def _dataset_id_collision_test(self, primary):
        """
        Assert that an attempt to create a dataset with a dataset_id that is
        already assigned somewhere on the cluster results in an error response
        and no configuration change.

        A configuration with two nodes, ``NODE_A`` and ``NODE_B``, is created.
        ``NODE_A`` is given one unattached manifestation.  An attempt is made
        to configure a new dataset is on ``primary`` which should be either
        ``NODE_A`` or ``NODE_B``.

        :return: A ``Deferred`` that fires with the result of the test.
        """
        dataset_id = unicode(uuid4())
        existing_dataset = Dataset(dataset_id=dataset_id)
        existing_manifestation = Manifestation(
            dataset=existing_dataset, primary=True)

        saving = self.persistence_service.save(Deployment(
            nodes={
                Node(
                    hostname=self.NODE_A,
                    other_manifestations=frozenset({existing_manifestation})
                ),
                Node(hostname=self.NODE_B),
            }
        ))

        def saved(ignored):
            return self.assertBadResult(
                b"POST", b"/datasets",
                {u"primary": primary, u"dataset_id": dataset_id},
                CONFLICT,
                {u"description": u"The provided dataset_id is already in use."}
            )
        posting = saving.addCallback(saved)

        def failed(reason):
            deployment = self.persistence_service.get()
            (node_a, node_b) = deployment.nodes
            if node_a.hostname != self.NODE_A:
                # They came out of the set backwards.
                node_a, node_b = node_b, node_a
            self.assertEqual(
                (frozenset({existing_manifestation}), frozenset()),
                (node_a.other_manifestations, node_b.other_manifestations)
            )

        posting.addCallback(failed)
        return posting

    def test_dataset_id_collision_different_node(self):
        """
        If the value for the ``dataset_id`` in the request body is already
        assigned to an existing dataset on a node other than the indicated
        primary, the response is an error indicating the collision and the
        dataset is not added to the desired configuration.
        """
        return self._dataset_id_collision_test(self.NODE_B)

    def test_dataset_id_collision_same_node(self):
        """
        If the value for the ``dataset_id`` in the request body is already
        assigned to an existing dataset on the indicated primary, the response
        is an error indicating the collision and the dataset is not added to
        the desired configuration.
        """
        return self._dataset_id_collision_test(self.NODE_A)

    def test_unknown_primary_node(self):
        """
        If a ``POST`` request made to the endpoint indicates a non-existent
        node as the location of the primary manifestation, the configuration is
        unchanged and an error response is returned to the client.
        """
        return self.assertBadResult(
            b"POST", b"/datasets", {u"primary": self.NODE_A},
            BAD_REQUEST, {
                u"description":
                    u"The provided primary node is not part of the cluster."
            }
        )
    test_unknown_primary_node.todo = (
        "See FLOC-1278.  Make this pass by inspecting cluster state "
        "instead of desired configuration to determine whether a node is "
        "valid or not."
    )

    def test_minimal_create_dataset(self):
        """
        If a ``POST`` request made to the endpoint includes just the minimum
        information necessary to create a new dataset (an identifier of the
        node on which to place its primary manifestation) then the desired
        configuration is updated to include a new unattached manifestation of
        the new dataset with a newly generated dataset identifier and a
        description of the new dataset is returned in a success response to the
        client.
        """
        creating = self.assertResponseCode(
            b"POST", b"/datasets", {u"primary": self.NODE_A},
            OK)
        creating.addCallback(readBody)
        creating.addCallback(loads)

        def got_result(result):
            result = result[u"result"]
            dataset_id = result.pop(u"dataset_id")
            self.assertEqual(
                {u"primary": self.NODE_A, u"metadata": {}}, result
            )
            deployment = self.persistence_service.get()
            self.assertEqual({dataset_id}, set(get_dataset_ids(deployment)))
        creating.addCallback(got_result)

        return creating

    def test_create_ignores_other_nodes(self):
        """
        Nodes in the configuration other than the one specified as the primary
        for the new dataset have their configuration left alone by the
        operation.
        """
        saving = self.persistence_service.save(Deployment(nodes={
            Node(hostname=self.NODE_A)
        }))

        def saved(ignored):
            return self.assertResponseCode(
                b"POST", b"/datasets", {u"primary": self.NODE_B}, OK
            )
        saving.addCallback(saved)

        def created(ignored):
            deployment = self.persistence_service.get()
            (node_a,) = (
                node
                for node
                in deployment.nodes
                if node.hostname == self.NODE_A
            )
            self.assertEqual(
                # No state, just like it started.
                Node(hostname=self.NODE_A),
                node_a
            )
        saving.addCallback(created)
        return saving

    def test_create_generates_different_dataset_ids(self):
        """
        If two ``POST`` requests are made to create two different datasets,
        each dataset created is assigned a distinct ``dataset_id``.
        """
        creating = gatherResults([
            self.assertResponseCode(
                b"POST", b"/datasets", {u"primary": self.NODE_A}, OK
            ).addCallback(readBody).addCallback(loads),
            self.assertResponseCode(
                b"POST", b"/datasets", {u"primary": self.NODE_A}, OK
            ).addCallback(readBody).addCallback(loads),
        ])

        def created(datasets):
            first = datasets[0][u"result"]
            second = datasets[1][u"result"]
            self.assertNotEqual(first[u"dataset_id"], second[u"dataset_id"])
        creating.addCallback(created)
        return creating

    def test_create_with_metadata(self):
        """
        Metadata included with the creation of a dataset is included in the
        persisted configuration and response body.
        """
        dataset_id = unicode(uuid4())
        metadata = {u"foo": u"bar", u"baz": u"quux"}
        dataset = {
            u"primary": self.NODE_A,
            u"dataset_id": dataset_id,
            u"metadata": metadata,
        }
        creating = self.assertGoodResult(
            b"POST", b"/datasets", dataset, dataset
        )

        def created(ignored):
            deployment = self.persistence_service.get()
            self.assertEqual(
                Deployment(nodes=frozenset({
                    Node(
                        hostname=self.NODE_A,
                        other_manifestations=frozenset({
                            Manifestation(
                                dataset=Dataset(
                                    dataset_id=dataset_id,
                                    metadata=pmap(metadata)
                                ),
                                primary=True
                            )
                        })
                    )
                })),
                deployment
            )
        creating.addCallback(created)
        return creating

    def test_create_with_maximum_size(self):
        """
        A maximum size included with the creation of a dataset is included in
        the persisted configuration and response body.
        """
        dataset_id = unicode(uuid4())
        maximum_size = 1024 * 1024 * 1024 * 42
        dataset = {
            u"primary": self.NODE_A,
            u"dataset_id": dataset_id,
            u"maximum_size": maximum_size,
        }
        response = dataset.copy()
        response[u"metadata"] = {}
        creating = self.assertGoodResult(
            b"POST", b"/datasets", dataset, response
        )

        def created(ignored):
            deployment = self.persistence_service.get()
            self.assertEqual(
                Deployment(nodes=frozenset({
                    Node(
                        hostname=self.NODE_A,
                        other_manifestations=frozenset({
                            Manifestation(
                                dataset=Dataset(
                                    dataset_id=dataset_id,
                                    maximum_size=maximum_size
                                ),
                                primary=True
                            )
                        })
                    )
                })),
                deployment
            )
        creating.addCallback(created)
        return creating


def get_dataset_ids(deployment):
    """
    Get an iterator of all of the ``dataset_id`` values on all nodes in the
    given deployment.

    :param Deployment deployment: The deployment to inspect.

    :return: An iterator of ``unicode`` giving the unique identifiers of all of
        the datasets.
    """
    for node in deployment.nodes:
        for manifestation in node.manifestations():
            yield manifestation.dataset.dataset_id

RealTestsCreateDataset, MemoryTestsCreateDataset = buildIntegrationTests(
    CreateDatasetTestsMixin, "CreateDataset", _build_app)


class CreateAPIServiceTests(SynchronousTestCase):
    """
    Tests for ``create_api_service``.
    """
    def test_returns_service(self):
        """
        ``create_api_service`` returns an object providing ``IService``.
        """
        reactor = MemoryReactor()
        endpoint = TCP4ServerEndpoint(reactor, 6789)
        verifyObject(IService, create_api_service(None, endpoint))

    def test_listens_endpoint(self):
        """
        ``create_api_service`` returns a service that listens using the given
        endpoint with a HTTP server.
        """
        reactor = MemoryReactor()
        endpoint = TCP4ServerEndpoint(reactor, 6789)
        service = create_api_service(None, endpoint)
        self.addCleanup(service.stopService)
        service.startService()
        server = reactor.tcpServers[0]
        port = server[0]
        factory = server[1].__class__
        self.assertEqual((port, factory), (6789, Site))
