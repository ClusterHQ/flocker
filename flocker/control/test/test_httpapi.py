# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
"""
Tests for ``flocker.control.httpapi``.
"""

from io import BytesIO
from uuid import uuid4

from pyrsistent import pmap, thaw

from zope.interface.verify import verifyObject

from twisted.internet import reactor
from twisted.internet.defer import gatherResults
from twisted.internet.endpoints import TCP4ServerEndpoint
from twisted.trial.unittest import SynchronousTestCase
from twisted.test.proto_helpers import MemoryReactor
from twisted.web.http import (
    CREATED, OK, CONFLICT, BAD_REQUEST, NOT_FOUND, INTERNAL_SERVER_ERROR,
    NOT_ALLOWED as METHOD_NOT_ALLOWED
)
from twisted.web.http_headers import Headers
from twisted.web.server import Site
from twisted.web.client import FileBodyProducer, readBody
from twisted.application.service import IService
from twisted.python.filepath import FilePath

from ...restapi.testtools import (
    buildIntegrationTests, dumps, loads)

from .. import (
    Application, Dataset, Manifestation, Node, NodeState,
    Deployment, AttachedVolume, DockerImage, Port
)
from ..httpapi import (
    ConfigurationAPIUserV1, create_api_service, datasets_from_deployment,
    api_dataset_from_dataset_and_node
)
from .._persistence import ConfigurationPersistenceService
from .._clusterstate import ClusterStateService
from ... import __version__


class APITestsMixin(object):
    """
    Helpers for writing integration tests for the Dataset Manager API.
    """
    # These addresses taken from RFC 5737 (TEST-NET-1)
    NODE_A = u"192.0.2.1"
    NODE_B = u"192.0.2.2"

    def initialize(self):
        """
        Create initial objects for the ``ConfigurationAPIUserV1``.
        """
        self.persistence_service = ConfigurationPersistenceService(
            reactor, FilePath(self.mktemp()))
        self.persistence_service.startService()
        self.cluster_state_service = ClusterStateService()
        self.cluster_state_service.startService()
        self.addCleanup(self.cluster_state_service.stopService)
        self.addCleanup(self.persistence_service.stopService)

    def assertResponseCode(self, method, path, request_body, expected_code):
        """
        Issue an HTTP request and make an assertion about the response code.

        :param bytes method: The HTTP method to use in the request.
        :param bytes path: The resource path to use in the request.
        :param dict request_body: A JSON-encodable object to encode (as JSON)
            into the request body.  Or ``None`` for no request body.
        :param int expected_code: The status code expected in the response.

        :return: A ``Deferred`` that will fire when the response has been
            received.  It will fire with a failure if the status code is
            not what was expected.  Otherwise it will fire with an
            ``IResponse`` provider representing the response.
        """
        if request_body is None:
            headers = None
            body_producer = None
        else:
            headers = Headers({b"content-type": [b"application/json"]})
            body_producer = FileBodyProducer(BytesIO(dumps(request_body)))

        requesting = self.agent.request(
            method, path, headers, body_producer
        )

        def check_code(response):
            self.assertEqual(expected_code, response.code)
            return response
        requesting.addCallback(check_code)
        return requesting

    def assertResult(self, method, path, request_body,
                     expected_code, expected_result):
        """
        Assert a particular JSON response for the given API request.

        :param bytes method: HTTP method to request.
        :param bytes path: HTTP path.
        :param unicode request_body: Body of HTTP request.
        :param int expected_code: The code expected in the response.
            response.
        :param list|dict expected_result: The body expected in the response.

        :return: A ``Deferred`` that fires when test is done.
        """
        requesting = self.assertResponseCode(
            method, path, request_body, expected_code)
        requesting.addCallback(readBody)
        requesting.addCallback(loads)

        def assertEqualAndReturn(expected, actual):
            """
            Assert that ``expected`` is equal to ``actual`` and return
            ``actual`` for further processing.
            """
            self.assertEqual(expected, actual)
            return actual

        requesting.addCallback(
            lambda actual_result: assertEqualAndReturn(
                expected_result, actual_result)
        )
        return requesting

    def assertResultItems(self, method, path, request_body,
                          expected_code, expected_result):
        """
        Assert a JSON array response for the given API request.

        The API returns a JSON array, which matches a Python list, by
        comparing that matching items exist in each sequence, but may
        appear in a different order.

        :param bytes method: HTTP method to request.
        :param bytes path: HTTP path.
        :param unicode request_body: Body of HTTP request.
        :param int expected_code: The code expected in the response.
        :param list expected_result: A list of items expects in a
            JSON array response.

        :return: A ``Deferred`` that fires when test is done.
        """
        requesting = self.assertResponseCode(
            method, path, request_body, expected_code)
        requesting.addCallback(readBody)
        requesting.addCallback(lambda body: self.assertItemsEqual(
            expected_result, loads(body)))
        return requesting


class VersionTestsMixin(APITestsMixin):
    """
    Tests for the service version description endpoint at ``/version``.
    """
    def test_version(self):
        """
        The ``/version`` command returns JSON-encoded ``__version__``.
        """
        return self.assertResult(
            b"GET", b"/version", None, OK, {u'flocker': __version__}
        )


def _build_app(test):
    test.initialize()
    return ConfigurationAPIUserV1(test.persistence_service,
                                  test.cluster_state_service).app
RealTestsAPI, MemoryTestsAPI = buildIntegrationTests(
    VersionTestsMixin, "API", _build_app)


class CreateContainerTestsMixin(APITestsMixin):
    """
    Tests for the container creation endpoint at ``/configuration/containers``.
    """
    def test_wrong_schema(self):
        """
        If a ``POST`` request made to the endpoint includes a body which
        doesn't match the ``definitions/containers`` schema, the response is
        an error indication a validation failure.
        """
        return self.assertResult(
            b"POST", b"/configuration/containers",
            {
                u"host": self.NODE_A,
                u"name": u'postgres',
                u'image': u'postgres',
                u"junk": u"garbage"
            },
            BAD_REQUEST, {
                u'description':
                    u"The provided JSON doesn't match the required schema.",
                u'errors': [
                    u"Additional properties are not allowed "
                    u"(u'junk' was unexpected)"
                ]
            }
        )

    def _container_name_collision_test(self, node1, node2):
        """
        Utility method to create two containers on the specified nodes.
        """
        # create a container
        d = self.assertResponseCode(
            b"POST", b"/configuration/containers",
            {
                u"host": node1, u"name": u"postgres", u"image": u"postgres"
            }, CREATED
        )
        # try to create another container with the same name
        d.addCallback(lambda _: self.assertResult(
            b"POST", b"/configuration/containers",
            {
                u"host": node2,
                u"name": u'postgres',
                u'image': u'postgres',
            },
            CONFLICT, {
                u'description':
                    u"The container name already exists.",
            }
        ))
        return d

    def test_container_name_collision_same_node(self):
        """
        A container will not be created if a container with the same name
        already exists on the node we are attempting to create on.
        """
        return self._container_name_collision_test(self.NODE_A, self.NODE_A)

    def test_container_name_collision_different_node(self):
        """
        A container will not be created if a container with the same name
        already exists on another node than the node we are attempting to
        create on.
        """
        return self._container_name_collision_test(self.NODE_A, self.NODE_B)

    def test_create_container_with_environment(self):
        """
        An API request to create a container including environment
        variables results in the existing configuration being updated.
        """
        saving = self.persistence_service.save(Deployment(
            nodes={
                Node(hostname=self.NODE_A),
                Node(hostname=self.NODE_B),
            }
        ))

        environment = {
            u'SITES_ENABLED_PATH': u'/etc/nginx/sites-enabled',
            u'CONFIG_FILE': u'/etc/nginx/nginx.conf',
        }

        saving.addCallback(lambda _: self.assertResponseCode(
            b"POST", b"/configuration/containers",
            {
                u"host": self.NODE_A, u"name": u"webserver",
                u"image": u"nginx", u"environment": environment
            }, CREATED
        ))

        def created(_):
            deployment = self.persistence_service.get()
            expected = Deployment(
                nodes={
                    Node(
                        hostname=self.NODE_A,
                        applications=[
                            Application(
                                name='webserver',
                                image=DockerImage.from_string('nginx'),
                                environment=frozenset(environment.items())
                            ),
                        ]
                    ),
                    Node(hostname=self.NODE_B),
                }
            )
            self.assertEqual(deployment, expected)

        saving.addCallback(created)
        return saving

    def test_create_container_with_environment_response(self):
        """
        An API request to create a container including environment
        variables returns the environment mapping supplied in the request in
        the response JSON.
        """
        environment = {
            u'SITES_ENABLED_PATH': u'/etc/nginx/sites-enabled',
            u'CONFIG_FILE': u'/etc/nginx/nginx.conf',
        }
        container_json = {
            u"host": self.NODE_B, u"name": u"webserver",
            u"image": u"nginx", u"environment": environment
        }
        container_json_result = {
            u"host": self.NODE_B, u"name": u"webserver",
            u"image": u"nginx:latest", u"environment": environment
        }
        return self.assertResult(
            b"POST", b"/configuration/containers",
            container_json, CREATED, container_json_result
        )

    def _test_conflicting_ports(self, node1, node2):
        """
        Utility method to create two containers with the same ports on two
        nodes.
        """
        d = self.assertResponseCode(
            b"POST", b"/configuration/containers",
            {
                u"host": node1, u"name": u"postgres",
                u"image": u"postgres",
                u"ports": [{u'internal': 5432, u'external': 54320}]
            }, CREATED
        )
        # try to create another container with the same ports
        d.addCallback(lambda _: self.assertResult(
            b"POST", b"/configuration/containers",
            {
                u"host": node2,
                u"name": u'another_postgres',
                u'image': u'postgres',
                u'ports': [{u'internal': 5432, u'external': 54320}]
            },
            CONFLICT, {
                u'description':
                    u"A specified external port is already in use.",
            }
        ))
        return d

    def test_create_container_with_conflicting_ports_different_node(self):
        """
        A valid API request to create a container including port mappings
        that conflict with the ports used by an application already running on
        the same node return an error and therefoer do not create the
        container.
        """
        return self._test_conflicting_ports(self.NODE_A, self.NODE_B)

    def test_create_container_with_conflicting_ports(self):
        """
        A valid API request to create a container including port mappings
        that conflict with the ports used by an application already running on
        the same node return an error and therefoer do not create the
        container.
        """
        return self._test_conflicting_ports(self.NODE_A, self.NODE_A)

    def test_create_container_with_ports(self):
        """
        A valid API request to create a container including port mappings
        results in an updated configuration.
        """
        saving = self.persistence_service.save(Deployment(
            nodes={
                Node(
                    hostname=self.NODE_A,
                    applications=[
                        Application(name='postgres',
                                    image=DockerImage.from_string('postgres'))
                    ]
                ),
                Node(hostname=self.NODE_B),
            }
        ))

        ports = [
            {'internal': 5432, 'external': 54320},
        ]

        saving.addCallback(lambda _: self.assertResponseCode(
            b"POST", b"/configuration/containers",
            {
                u"host": self.NODE_A, u"name": u"another_postgres",
                u"image": u"postgres", u"ports": ports
            }, CREATED
        ))

        def created(_):
            application_ports = [Port(internal_port=5432, external_port=54320)]
            deployment = self.persistence_service.get()
            expected = Deployment(
                nodes={
                    Node(
                        hostname=self.NODE_A,
                        applications=[
                            Application(
                                name='postgres',
                                image=DockerImage.from_string('postgres')
                            ),
                            Application(
                                name='another_postgres',
                                image=DockerImage.from_string('postgres'),
                                ports=frozenset(application_ports)
                            )
                        ]
                    ),
                    Node(hostname=self.NODE_B),
                }
            )
            self.assertEqual(deployment, expected)

        saving.addCallback(created)
        return saving

    def test_create_container_with_ports_response(self):
        """
        A valid API request to create a container including port mappings
        returns the port mapping supplied in the request in the response JSON.
        """
        ports = [
            {'internal': 5432, 'external': 54320},
        ]
        container_json = {
            u"host": self.NODE_B, u"name": u"postgres",
            u"image": u"postgres", u"ports": ports
        }
        container_json_result = {
            u"host": self.NODE_B, u"name": u"postgres",
            u"image": u"postgres:latest", u"ports": ports
        }
        return self.assertResult(
            b"POST", b"/configuration/containers",
            container_json, CREATED, container_json_result
        )

    def test_configuration_updated_existing_node(self):
        """
        A valid API request to create a container on an existing node results
        in an updated configuration.
        """
        saving = self.persistence_service.save(Deployment(
            nodes={
                Node(
                    hostname=self.NODE_A,
                    applications=[
                        Application(name='postgres',
                                    image=DockerImage.from_string('postgres'))
                    ]
                ),
                Node(hostname=self.NODE_B),
            }
        ))

        saving.addCallback(lambda _: self.assertResponseCode(
            b"POST", b"/configuration/containers",
            {
                u"host": self.NODE_A, u"name": u"another_postgres",
                u"image": u"postgres"
            }, CREATED
        ))

        def created(_):
            deployment = self.persistence_service.get()
            expected = Deployment(
                nodes={
                    Node(
                        hostname=self.NODE_A,
                        applications=[
                            Application(
                                name='postgres',
                                image=DockerImage.from_string('postgres')
                            ),
                            Application(
                                name='another_postgres',
                                image=DockerImage.from_string('postgres')
                            )
                        ]
                    ),
                    Node(hostname=self.NODE_B),
                }
            )
            self.assertEqual(deployment, expected)

        saving.addCallback(created)
        return saving

    def test_configuration_updated_new_node(self):
        """
        A valid API request to create a container on a new node results
        in an updated configuration.
        """
        d = self.assertResponseCode(
            b"POST", b"/configuration/containers",
            {
                u"host": self.NODE_B, u"name": u"postgres",
                u"image": u"postgres"
            }, CREATED
        )

        def created(_):
            deployment = self.persistence_service.get()
            expected = Deployment(
                nodes={
                    Node(
                        hostname=self.NODE_B,
                        applications=[
                            Application(
                                name='postgres',
                                image=DockerImage.from_string('postgres')
                            ),
                        ]
                    ),
                }
            )
            self.assertEqual(deployment, expected)

        d.addCallback(created)
        return d

    def test_response(self):
        """
        A minimally valid API request to create a container returns the
        expected JSON response.
        """
        container_json = {
            u"host": self.NODE_B, u"name": u"postgres",
            u"image": u"postgres"
        }
        container_json_result = {
            u"host": self.NODE_B, u"name": u"postgres",
            u"image": u"postgres:latest"
        }
        return self.assertResult(
            b"POST", b"/configuration/containers",
            container_json, CREATED, container_json_result
        )


RealTestsCreateContainer, MemoryTestsCreateContainer = buildIntegrationTests(
    CreateContainerTestsMixin, "CreateContainer", _build_app)


class DeleteContainerTestsMixin(APITestsMixin):
    """
    Tests for the container removal endpoint at
    ``/configuration/datasets/<dataset_id>``.
    """
    def test_unknown_container(self):
        """
        NOT_FOUND is returned if the requested container doesn't exist.
        """
        unknown_name = u"xxx"
        return self.assertResult(
            b"DELETE",
            b"/configuration/containers/%s" % (
                unknown_name.encode('ascii'),),
            None, NOT_FOUND,
            {u"description": u'Container not found.'})

    def _delete_test(self, name):
        """
        Create and then delete a container, ensuring the expected response
        code of OK from deletion.

        :param Application application: The container which will be deleted.
        :returns: A ``Deferred`` which fires when all assertions have been
            executed.
        """
        d = self.assertResponseCode(
            b"POST", b"/configuration/containers",
            {
                u"host": self.NODE_A, u"name": name,
                u"image": u"postgres"
            }, CREATED
        )
        d.addCallback(lambda _: self.assertResult(
            b"DELETE",
            u"/configuration/containers/{}".format(name).encode("ascii"), None,
            OK, None,
        ))
        return d

    def test_delete(self):
        """
        The ``DELETE`` method removes the given container from the
        configuration.
        """
        d = self._delete_test(u"mycontainer")

        def deleted(_):
            deployment = self.persistence_service.get()
            origin = next(iter(deployment.nodes))
            self.assertEqual(list(origin.applications), [])
        d.addCallback(deleted)
        return d

    def test_delete_leaves_others(self):
        """
        The ``DELETE`` method does not remove unrelated containers.
        """
        d = self.assertResponseCode(
            b"POST", b"/configuration/containers",
            {
                u"host": self.NODE_A, u"name": u"somecontainer",
                u"image": u"postgres"
            }, CREATED
        )
        d.addCallback(lambda _: self._delete_test(u"mycontainer"))

        def deleted(_):
            deployment = self.persistence_service.get()
            origin = next(iter(deployment.nodes))
            self.assertEqual(
                list(origin.applications),
                [Application(name=u"somecontainer",
                             image=DockerImage.from_string(u"postgres"))])
        d.addCallback(deleted)
        return d


RealTestsDeleteContainer, MemoryTestsDeleteContainer = (
    buildIntegrationTests(
        DeleteContainerTestsMixin, "DeleteContainer", _build_app)
)


class CreateDatasetTestsMixin(APITestsMixin):
    """
    Tests for the dataset creation endpoint at ``/configuration/datasets``.
    """
    def test_wrong_schema(self):
        """
        If a ``POST`` request made to the endpoint includes a body which
        doesn't match the ``definitions/datasets`` schema, the response is an
        error indication a validation failure.
        """
        return self.assertResult(
            b"POST", b"/configuration/datasets",
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

    def _dataset_id_collision_test(self, primary, modifier=lambda uuid: uuid):
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
                    manifestations={existing_manifestation.dataset_id:
                                    existing_manifestation}
                ),
                Node(hostname=self.NODE_B),
            }
        ))

        def saved(ignored):
            return self.assertResult(
                b"POST", b"/configuration/datasets",
                {u"primary": primary, u"dataset_id": modifier(dataset_id)},
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
                ({existing_manifestation.dataset_id: existing_manifestation},
                 {}),
                (node_a.manifestations, node_b.manifestations)
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

    def test_dataset_id_collision_different_case(self):
        """
        If the value for the ``dataset_id`` in the request body differs only in
        alphabetic case from a ``dataset_id`` assigned to an existing dataset,
        the response is an error indicating the collision and the dataset is
        not added to the desired configuration.
        """
        return self._dataset_id_collision_test(self.NODE_A, unicode.title)

    def test_unknown_primary_node(self):
        """
        If a ``POST`` request made to the endpoint indicates a non-existent
        node as the location of the primary manifestation, the configuration is
        unchanged and an error response is returned to the client.
        """
        return self.assertResult(
            b"POST", b"/configuration/datasets", {u"primary": self.NODE_A},
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
            b"POST", b"/configuration/datasets", {u"primary": self.NODE_A},
            CREATED)
        creating.addCallback(readBody)
        creating.addCallback(loads)

        def got_result(result):
            dataset_id = result.pop(u"dataset_id")
            self.assertEqual(
                {u"primary": self.NODE_A, u"metadata": {}, u"deleted": False},
                result
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
                b"POST", b"/configuration/datasets", {u"primary": self.NODE_B},
                CREATED
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
                b"POST", b"/configuration/datasets", {u"primary": self.NODE_A},
                CREATED
            ).addCallback(readBody).addCallback(loads),
            self.assertResponseCode(
                b"POST", b"/configuration/datasets", {u"primary": self.NODE_A},
                CREATED
            ).addCallback(readBody).addCallback(loads),
        ])

        def created(datasets):
            first = datasets[0]
            second = datasets[1]
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
        expected = dataset.copy()
        expected[u"deleted"] = False
        creating = self.assertResult(
            b"POST", b"/configuration/datasets", dataset, CREATED, expected
        )

        def created(ignored):
            deployment = self.persistence_service.get()
            self.assertEqual(
                Deployment(nodes=frozenset({
                    Node(
                        hostname=self.NODE_A,
                        manifestations={
                            dataset_id: Manifestation(
                                dataset=Dataset(
                                    dataset_id=dataset_id,
                                    metadata=pmap(metadata)
                                ),
                                primary=True
                            )
                        }
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
        response[u"deleted"] = False
        creating = self.assertResult(
            b"POST", b"/configuration/datasets", dataset, CREATED, response
        )

        def created(ignored):
            deployment = self.persistence_service.get()
            self.assertEqual(
                Deployment(nodes=frozenset({
                    Node(
                        hostname=self.NODE_A,
                        manifestations={
                            dataset_id: Manifestation(
                                dataset=Dataset(
                                    dataset_id=dataset_id,
                                    maximum_size=maximum_size
                                ),
                                primary=True
                            )
                        }
                    )
                })),
                deployment
            )
        creating.addCallback(created)
        return creating


class UpdatePrimaryDatasetTestsMixin(APITestsMixin):
    """
    Tests for the dataset modification endpoint at
    ``/configuration/datasets/<dataset_id>``.
    """
    def test_unknown_dataset(self):
        """
        NOT_FOUND is returned if the requested dataset_id doesn't exist.
        The error includes the requested dataset_id.
        """
        unknown_dataset_id = unicode(uuid4())
        return self.assertResult(
            b"POST",
            b"/configuration/datasets/%s" % (
                unknown_dataset_id.encode('ascii'),),
            {u'primary': self.NODE_A},
            NOT_FOUND,
            {u"description": u'Dataset not found.'})

    def _test_change_primary(self, dataset, deployment, origin, target):
        """
        Helper method which pre-populates the persistence_service with the
        supplied ``dataset``, makes an API call to move the supplied
        ``dataset`` from ``origin`` to ``target`` and finally asserts that the
        API call returned the expected result and that the persistence_service
        has been updated.

        :param Dataset dataset: The dataset which will be moved.
        :param Deployment deployment: The deployment that contains the dataset.
        :param bytes origin: The node IP address of the node that holds the
            current primary manifestation of the ``dataset``.
        :param bytes target: The node IP address of the node to which the
            dataset will be moved.
        :returns: A ``Deferred`` which fires when all assertions have been
            executed.
        """
        expected_dataset_id = dataset.dataset_id

        expected_dataset = {
            u"dataset_id": expected_dataset_id,
            u"primary": target,
            u"metadata": {},
            u"deleted": False,
        }

        saving = self.persistence_service.save(deployment)

        def saved(ignored):
            creating = self.assertResult(
                b"POST",
                b"/configuration/datasets/%s" % (
                    expected_dataset_id.encode('ascii'),),
                {u"primary": target},
                OK,
                expected_dataset
            )

            def got_result(result):
                deployment = self.persistence_service.get()
                for node in deployment.nodes:
                    if node.hostname == target:
                        dataset_ids = [
                            (m.primary, m.dataset.dataset_id)
                            for m in node.manifestations.values()
                        ]
                        self.assertIn((True, expected_dataset_id), dataset_ids)
                        break
                else:
                    self.fail('Node not found. {}'.format(target))

            creating.addCallback(got_result)
            return creating
        saving.addCallback(saved)
        return saving

    def test_change_primary_to_unconfigured_node(self):
        """
        If a different primary IP address is supplied and it identifies a node
        which is not yet part of the cluster configuration, the modification
        request succeeds and the dataset's primary becomes the given address.
        """
        expected_manifestation = _manifestation()
        current_primary_node = Node(
            hostname=self.NODE_A,
            applications=frozenset(),
            manifestations={expected_manifestation.dataset_id:
                            expected_manifestation}
        )
        deployment = Deployment(nodes=frozenset([current_primary_node]))

        return self._test_change_primary(
            expected_manifestation.dataset, deployment,
            self.NODE_A, self.NODE_B
        )

    def test_unknown_primary_node(self):
        """
        A dataset's primary IP address must belong to a node in the cluster.
        XXX: Skip this test until FLOC-1278 is implemented.

        This is an alternative to the behaviour above.
        The dataset creation API currently behaves this way.
        Perhaps it shouldn't.
        And instead allow datasets to be created with an as yet unknown node.
        """
        expected_manifestation = _manifestation()
        node_a = Node(
            hostname=self.NODE_A,
            applications=frozenset(),
            manifestations={expected_manifestation.dataset_id:
                            expected_manifestation}
        )
        deployment = Deployment(nodes=frozenset([node_a]))
        saving = self.persistence_service.save(deployment)

        def saved(ignored):
            creating = self.assertResult(
                b"POST",
                b"/configuration/datasets/%s" % (
                    expected_manifestation.dataset.dataset_id.encode('ascii')
                ),
                {u"primary": self.NODE_B},
                BAD_REQUEST, {
                    u"description":
                    u"The provided primary node is not part of the cluster."
                }
            )
            return creating
        saving.addCallback(saved)
        return saving
    test_unknown_primary_node.todo = (
        "See FLOC-1278.  Make this pass by inspecting cluster state "
        "instead of desired configuration to determine whether a node is "
        "valid or not."
    )

    def test_change_primary_to_configured_node(self):
        """
        If a different primary IP address is supplied and it identifies a node
        which is already part of the cluster configuration, the modification
        request succeeds and the dataset's primary becomes the given address.
        """
        expected_manifestation = _manifestation()
        node_a = Node(
            hostname=self.NODE_A,
            applications=frozenset(),
            manifestations={expected_manifestation.dataset_id:
                            expected_manifestation}
        )
        node_b = Node(hostname=self.NODE_B)
        deployment = Deployment(nodes=frozenset([node_a, node_b]))
        return self._test_change_primary(
            expected_manifestation.dataset, deployment,
            self.NODE_A, self.NODE_B
        )

    def test_primary_unchanged(self):
        """
        If the current primary IP address is supplied, the modification request
        succeeds.
        """
        expected_manifestation = _manifestation()
        node_a = Node(
            hostname=self.NODE_A,
            applications=frozenset(),
            manifestations={expected_manifestation.dataset_id:
                            expected_manifestation}
        )
        node_b = Node(hostname=self.NODE_B)
        deployment = Deployment(nodes=frozenset([node_a, node_b]))
        return self._test_change_primary(
            expected_manifestation.dataset, deployment,
            self.NODE_A, self.NODE_A
        )

    def test_only_replicas(self):
        """
        If there are only replica manifestations of the requested dataset, 500
        response is returned and ``IndexError`` is logged.

        XXX The 500 error message really should be clearer.
        See https://clusterhq.atlassian.net/browse/FLOC-1393

        XXX This situation should return a more friendly error code and
        message.
        See https://clusterhq.atlassian.net/browse/FLOC-1403.
        """
        expected_manifestation = _manifestation(primary=False)
        node_a = Node(
            hostname=self.NODE_A,
            applications=frozenset(),
            manifestations={expected_manifestation.dataset_id:
                            expected_manifestation}
        )
        node_b = Node(hostname=self.NODE_B)
        deployment = Deployment(nodes=frozenset([node_a, node_b]))
        saving = self.persistence_service.save(deployment)

        def saved(ignored):
            creating = self.assertResult(
                b"POST",
                b"/configuration/datasets/%s" % (
                    expected_manifestation.dataset.dataset_id.encode('ascii')
                ),
                {u"primary": self.NODE_B},
                INTERNAL_SERVER_ERROR,
                u'ELIOT LOG REFERENCE'
            )
            return creating
        saving.addCallback(saved)
        return saving
    test_only_replicas.todo = (
        "XXX: Perhaps this test isn't necessary. "
        "There should always be a primary."
        "But perhaps there should be a test that demonstrates the general 500 "
        "response message format."
        "See https://clusterhq.atlassian.net/browse/FLOC-1393 and "
        "https://clusterhq.atlassian.net/browse/FLOC-1403"
    )

    def test_primary_invalid(self):
        """
        A request with an invalid (non-IPv4) primary IP address is rejected
        with ``BAD_REQUEST``.
        """
        expected_manifestation = _manifestation()
        node_a = Node(
            hostname=self.NODE_A,
            applications=frozenset(),
            manifestations={expected_manifestation.dataset_id:
                            expected_manifestation}
        )
        deployment = Deployment(nodes=frozenset([node_a]))
        saving = self.persistence_service.save(deployment)

        def saved(ignored):
            creating = self.assertResponseCode(
                b"POST",
                b"/configuration/datasets/%s" % (
                    expected_manifestation.dataset.dataset_id.encode('ascii')
                ),
                {u"primary": u'192.0.2.257'},
                BAD_REQUEST,
            )
            return creating
        saving.addCallback(saved)
        return saving

    def test_no_primary(self):
        """
        An update request without a primary address is allowed.
        """
        expected_manifestation = _manifestation()
        node_a = Node(
            hostname=self.NODE_A,
            applications=frozenset(),
            manifestations={expected_manifestation.dataset_id:
                            expected_manifestation},
        )
        deployment = Deployment(nodes=frozenset([node_a]))
        saving = self.persistence_service.save(deployment)

        def saved(ignored):
            creating = self.assertResponseCode(
                b"POST",
                b"/configuration/datasets/%s" % (
                    expected_manifestation.dataset.dataset_id.encode('ascii')
                ),
                {},
                OK,
            )
            return creating
        saving.addCallback(saved)
        return saving
    test_no_primary.todo = (
        'It should be possible to submit a dataset update request without a '
        'primary address, but the input schema currently requires the primary '
        'attribute. This will need to be addressed before or as part of '
        'https://clusterhq.atlassian.net/browse/FLOC-1404'
    )

RealTestsUpdatePrimaryDataset, MemoryTestsUpdatePrimaryDataset = (
    buildIntegrationTests(
        UpdatePrimaryDatasetTestsMixin, "UpdatePrimaryDataset", _build_app)
)


class DeleteDatasetTestsMixin(APITestsMixin):
    """
    Tests for the dataset deletion endpoint at
    ``/configuration/datasets/<dataset_id>``.
    """
    def test_unknown_dataset(self):
        """
        NOT_FOUND is returned if the requested dataset_id doesn't exist.
        The error includes the requested dataset_id.
        """
        unknown_dataset_id = unicode(uuid4())
        return self.assertResult(
            b"DELETE",
            b"/configuration/datasets/%s" % (
                unknown_dataset_id.encode('ascii'),),
            None, NOT_FOUND,
            {u"description": u'Dataset not found.'})

    def _test_delete(self, dataset):
        """
        Helper method which makes an API call to delete the supplied
        ``dataset`` from ``origin`` and finally asserts that the API call
        returned the expected result and that the persistence_service has
        been updated.

        :param Dataset dataset: The dataset which will be deleted.
        :returns: A ``Deferred`` which fires when all assertions have been
            executed.
        """
        deployment = self.persistence_service.get()
        expected_dataset_id = dataset.dataset_id
        # There's only one node:
        origin = next(iter(deployment.nodes))

        expected_dataset = {
            u"dataset_id": expected_dataset_id,
            u"primary": origin.hostname,
            u"metadata": {},
            u"deleted": True,
        }

        deleting = self.assertResult(
            b"DELETE",
            b"/configuration/datasets/%s" % (
                expected_dataset_id.encode('ascii'),),
            None, OK, expected_dataset
        )

        def got_result(result):
            deployment = self.persistence_service.get()
            for node in deployment.nodes:
                if node.hostname == origin.hostname:
                    dataset_ids = [
                        (m.dataset.deleted, m.dataset.dataset_id)
                        for m in node.manifestations.values()
                    ]
                    self.assertIn((True, expected_dataset_id), dataset_ids)
                    break
            else:
                self.fail('Node not found. {}'.format(node.hostname))

        deleting.addCallback(got_result)
        return deleting

    def _setup_manifestation(self):
        """
        Create and save a configuration with a single node that has a
        manifestation.

        :return: ``Deferred`` firing with the newly created
            ``Manifestation`` that ``_test_delete`` can delete.
        """
        expected_manifestation = _manifestation()
        node_a = Node(
            hostname=self.NODE_A,
            applications=frozenset(),
            manifestations={expected_manifestation.dataset_id:
                            expected_manifestation}
        )
        d = self.persistence_service.save(
            Deployment(nodes=frozenset([node_a])))
        d.addCallback(lambda _: expected_manifestation)
        return d

    def test_delete(self):
        """
        The ``DELETE`` action sets the ``deleted`` attribute to true on the
        given dataset.
        """
        d = self._setup_manifestation()
        d.addCallback(lambda manifestation: self._test_delete(
            manifestation.dataset))
        return d

    def test_delete_idempotent(self):
        """
        The ``DELETE`` action on an already ``deleted`` dataset has same
        response as original deletion.
        """
        created = self._setup_manifestation()

        def got_manifestation(expected_manifestation):
            d = self._test_delete(expected_manifestation.dataset)
            d.addCallback(lambda _: self._test_delete(expected_manifestation))
            return d
        created.addCallback(got_manifestation)
        return created

    def test_update_deleted(self):
        """
        Attempting to update a deleted dataset results in a Method Not Allowed
        error.
        """
        created = self._setup_manifestation()

        def got_manifestation(expected_manifestation):
            d = self._test_delete(expected_manifestation.dataset)
            d.addCallback(lambda _: self.assertResult(
                b"POST",
                b"/configuration/datasets/%s" % (
                    expected_manifestation.dataset_id.encode('ascii')
                ),
                {u"primary": u"192.168.1.1"},
                METHOD_NOT_ALLOWED, {
                    u"description":
                    u"The dataset has been deleted."
                }
            ))
            return d
        created.addCallback(got_manifestation)
        return created

    def test_multiple_manifestations(self):
        """
        If there are multiple manifestations on multiple nodes the ``DELETE``
        action will mark all of their datasets as deleted.
        """
        raise NotImplementedError()
    test_multiple_manifestations.todo = "Implement in FLOC-1240"


RealTestsDeleteDataset, MemoryTestsDeleteDataset = (
    buildIntegrationTests(
        DeleteDatasetTestsMixin, "DeleteDataset", _build_app)
)


def get_dataset_ids(deployment):
    """
    Get an iterator of all of the ``dataset_id`` values on all nodes in the
    given deployment.

    :param Deployment deployment: The deployment to inspect.

    :return: An iterator of ``unicode`` giving the unique identifiers of all of
        the datasets.
    """
    for node in deployment.nodes:
        for manifestation in node.manifestations.values():
            yield manifestation.dataset.dataset_id


RealTestsCreateDataset, MemoryTestsCreateDataset = buildIntegrationTests(
    CreateDatasetTestsMixin, "CreateDataset", _build_app)


def _manifestation(**kwargs):
    """
    :param kwargs: Additional keyword arguments to use to initialize the
        manifestation's ``Dataset``.
        If ``kwargs`` includes a ``primary`` key its value will be supplied to
        the ``Manifestation`` initialiser as the ``primary`` argument in order
        to control whether to create a primary or replica
        ``Manifestation``. Defaults to ``True``.

    :return: A ``Manifestation`` for a dataset with a new
        random identifier.
    """
    primary = kwargs.pop('primary', True)
    dataset_id = unicode(uuid4())
    existing_dataset = Dataset(dataset_id=dataset_id, **kwargs)
    return Manifestation(dataset=existing_dataset, primary=primary)


class GetDatasetConfigurationTestsMixin(APITestsMixin):
    """
    Tests for the dataset configuration retrieval endpoint at
    ``/datasets``.
    """
    def test_empty(self):
        """
        When the cluster configuration includes no datasets, the
        endpoint returns an empty list.
        """
        return self.assertResult(
            b"GET", b"/configuration/datasets", None, OK, []
        )

    def _dataset_test(self, deployment, expected):
        """
        Verify that when the control service has ``deployment``
        persisted as its configuration, the response from the
        configuration listing endpoint includes the items in
        ``expected``.

        :param Deployment deployment: The deployment configuration to
            use.

        :param list expected: The objects expected to be returned by
            the endpoint, disregarding order.

        :return: A ``Deferred`` that fires successfully if the
            expected results are received or which fires with a
            failure if there is a problem.
        """
        saving = self.persistence_service.save(deployment)

        def saved(ignored):
            return self.assertResultItems(
                b"GET", b"/configuration/datasets", None, OK, expected
            )
        saving.addCallback(saved)
        return saving

    def _one_dataset_test(self, **kwargs):
        """
        Assert that when a single manifestation exists on the cluster a ``GET``
        request to the ``/configuration/datasets`` returns a list of one object
        that represents that manifestation.

        :param kwargs: Additional arguments to use when creating the
            manifestation.  See ``_manifestation``.

        :return: A ``Deferred`` that fires when the assertion has been made.
        """
        manifestation = _manifestation(**kwargs)
        deployment = Deployment(
            nodes={
                Node(
                    hostname=self.NODE_A,
                    manifestations={manifestation.dataset_id:
                                    manifestation},
                ),
            },
        )
        expected = [
            api_dataset_from_dataset_and_node(
                manifestation.dataset, self.NODE_A
            )
        ]
        return self._dataset_test(deployment, expected)

    def test_one_dataset(self):
        """
        When the cluster configuration includes one dataset, the
        endpoint returns a single-element list containing the dataset.
        """
        return self._one_dataset_test()

    def test_dataset_with_other_properties(self):
        """
        A dataset with a maximum size and non-empty metadata has both
        of those values included in the response from the endpoint.
        """
        return self._one_dataset_test(
            maximum_size=1024 * 1024 * 100, metadata=pmap({u"foo": u"bar"})
        )

    def test_several_nodes(self):
        """
        When the cluster configuration includes several nodes, each
        with a dataset, the endpoint returns a list containing
        information for the dataset on each node.
        """
        manifestation_a = _manifestation()
        manifestation_b = _manifestation()
        deployment = Deployment(
            nodes={
                Node(
                    hostname=self.NODE_A,
                    manifestations={manifestation_a.dataset_id:
                                    manifestation_a},
                ),
                Node(
                    hostname=self.NODE_B,
                    manifestations={manifestation_b.dataset_id:
                                    manifestation_b},
                ),
            },
        )
        expected = [
            api_dataset_from_dataset_and_node(
                manifestation_a.dataset, self.NODE_A
            ),
            api_dataset_from_dataset_and_node(
                manifestation_b.dataset, self.NODE_B
            ),
        ]
        return self._dataset_test(deployment, expected)

    def test_several_datasets(self):
        """
        When the cluster configuration includes a node with several
        datasets, the endpoint returns a list containing information
        for each dataset.
        """
        manifestation_a = _manifestation()
        manifestation_b = _manifestation()
        deployment = Deployment(
            nodes={
                Node(
                    hostname=self.NODE_A,
                    manifestations={
                        manifestation_a.dataset_id: manifestation_a,
                        manifestation_b.dataset_id: manifestation_b,
                    },
                ),
            },
        )
        expected = [
            api_dataset_from_dataset_and_node(
                manifestation_a.dataset, self.NODE_A
            ),
            api_dataset_from_dataset_and_node(
                manifestation_b.dataset, self.NODE_A
            ),
        ]
        return self._dataset_test(deployment, expected)


RealTestsGetDatasetConfiguration, MemoryTestsGetDatasetConfiguration = (
    buildIntegrationTests(
        GetDatasetConfigurationTestsMixin, "GetDatasetConfiguration",
        _build_app
    )
)


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
        verifyObject(IService, create_api_service(None, None, endpoint))

    def test_listens_endpoint(self):
        """
        ``create_api_service`` returns a service that listens using the given
        endpoint with a HTTP server.
        """
        reactor = MemoryReactor()
        endpoint = TCP4ServerEndpoint(reactor, 6789)
        service = create_api_service(None, None, endpoint)
        self.addCleanup(service.stopService)
        service.startService()
        server = reactor.tcpServers[0]
        port = server[0]
        factory = server[1].__class__
        self.assertEqual((port, factory), (6789, Site))


class DatasetsStateTestsMixin(APITestsMixin):
    """
    Tests for the service datasets state description endpoint at
    ``/state/datasets``.
    """
    def test_empty(self):
        """
        When the cluster state includes no datasets, the endpoint
        returns an empty list.
        """
        response = []
        return self.assertResult(
            b"GET", b"/state/datasets", None, OK, response
        )

    def test_one_dataset(self):
        """
        When the cluster state includes one dataset, the endpoint
        returns a single-element list containing the dataset.
        """
        expected_dataset = Dataset(dataset_id=unicode(uuid4()))
        expected_manifestation = Manifestation(
            dataset=expected_dataset, primary=True)
        expected_hostname = u"192.0.2.101"
        self.cluster_state_service.update_node_state(
            NodeState(
                hostname=expected_hostname,
                running=[],
                not_running=[],
                manifestations={expected_manifestation},
                paths={expected_dataset.dataset_id: FilePath(b"/path/dataset")}
            )
        )
        expected_dict = dict(
            dataset_id=expected_dataset.dataset_id,
            primary=expected_hostname,
            path=u"/path/dataset",
        )
        response = [expected_dict]
        return self.assertResult(
            b"GET", b"/state/datasets", None, OK, response
        )

    def test_two_datasets(self):
        """
        When the cluster state includes more than one dataset, the endpoint
        returns a list containing the datasets in arbitrary order.
        """
        expected_dataset1 = Dataset(dataset_id=unicode(uuid4()))
        expected_manifestation1 = Manifestation(
            dataset=expected_dataset1, primary=True)
        expected_hostname1 = u"192.0.2.101"
        expected_dataset2 = Dataset(dataset_id=unicode(uuid4()))
        expected_manifestation2 = Manifestation(
            dataset=expected_dataset2, primary=True)
        expected_hostname2 = u"192.0.2.102"
        self.cluster_state_service.update_node_state(
            NodeState(
                hostname=expected_hostname1,
                running=[],
                not_running=[],
                manifestations={expected_manifestation1},
                paths={expected_dataset1.dataset_id: FilePath(b"/aa")},
            )
        )
        self.cluster_state_service.update_node_state(
            NodeState(
                hostname=expected_hostname2,
                running=[],
                not_running=[],
                manifestations={expected_manifestation2},
                paths={expected_dataset2.dataset_id: FilePath(b"/bb")},
            )
        )
        expected_dict1 = dict(
            dataset_id=expected_dataset1.dataset_id,
            primary=expected_hostname1,
            path=u"/aa",
        )
        expected_dict2 = dict(
            dataset_id=expected_dataset2.dataset_id,
            primary=expected_hostname2,
            path=u"/bb",
        )
        response = [expected_dict1, expected_dict2]
        return self.assertResultItems(
            b"GET", b"/state/datasets", None, OK, response
        )

RealTestsDatasetsStateAPI, MemoryTestsDatasetsStateAPI = buildIntegrationTests(
    DatasetsStateTestsMixin, "DatasetsStateAPI", _build_app)


class DatasetsFromDeploymentTests(SynchronousTestCase):
    """
    Tests for ``datasets_from_deployment``.
    """
    def test_empty(self):
        """
        ``datasets_from_deployment`` returns an empty list if no Manifestations
        are found in the supplied Deployment.
        """
        deployment = Deployment(nodes=frozenset())
        expected = []
        self.assertEqual(expected, list(datasets_from_deployment(deployment)))

    def test_application_volumes(self):
        """
        ``datasets_from_deployment`` returns dataset dictionaries for the
        volumes attached to applications on all nodes.
        """
        expected_hostname = u"node1.example.com"
        expected_dataset = Dataset(dataset_id=u"jalkjlk")
        volume = AttachedVolume(
            manifestation=Manifestation(dataset=expected_dataset,
                                        primary=True),
            mountpoint=FilePath(b"/blah"))

        node = Node(
            hostname=expected_hostname,
            applications={
                Application(
                    name=u'mysql-clusterhq',
                    image=DockerImage.from_string(u"xxx")),
                Application(name=u'site-clusterhq.com',
                            image=DockerImage.from_string(u"xxx"),
                            volume=volume)},
            manifestations={expected_dataset.dataset_id:
                            volume.manifestation},
        )

        deployment = Deployment(nodes=frozenset([node]))
        expected = dict(
            dataset_id=expected_dataset.dataset_id,
            primary=expected_hostname,
            metadata=thaw(expected_dataset.metadata),
            deleted=False,
        )
        self.assertEqual(
            [expected], list(datasets_from_deployment(deployment)))

    def test_other_manifestations(self):
        """
        ``datasets_from_deployment`` returns dataset dictionaries for the
        other_manifestations on all nodes.
        """
        expected_hostname = u"node1.example.com"
        expected_dataset = Dataset(dataset_id=u"jalkjlk")
        expected_manifestation = Manifestation(dataset=expected_dataset,
                                               primary=True)
        node = Node(
            hostname=expected_hostname,
            applications=frozenset(),
            manifestations={expected_manifestation.dataset_id:
                            expected_manifestation},
        )

        deployment = Deployment(nodes=frozenset([node]))
        expected = dict(
            dataset_id=expected_dataset.dataset_id,
            primary=expected_hostname,
            metadata=thaw(expected_dataset.metadata),
            deleted=False,
        )
        self.assertEqual(
            [expected], list(datasets_from_deployment(deployment)))

    def test_primary_and_replica_manifestations(self):
        """
        ``datasets_from_deployment`` does not return replica manifestations
        on other nodes.
        """

        expected_hostname = u"node1.example.com"
        expected_dataset = Dataset(dataset_id=u"jalkjlk")
        volume = AttachedVolume(
            manifestation=Manifestation(dataset=expected_dataset,
                                        primary=True),
            mountpoint=FilePath(b"/blah"))

        node1 = Node(
            hostname=expected_hostname,
            applications=frozenset({
                Application(
                    name=u'mysql-clusterhq',
                    image=DockerImage.from_string("mysql")),
                Application(name=u'site-clusterhq.com',
                            image=DockerImage.from_string("site"),
                            volume=volume)}),
            manifestations={expected_dataset.dataset_id: volume.manifestation},
        )
        expected_manifestation = Manifestation(dataset=expected_dataset,
                                               primary=False)
        node2 = Node(
            hostname=u"node2.example.com",
            applications=frozenset(),
            manifestations={expected_manifestation.dataset_id:
                            expected_manifestation},
        )

        deployment = Deployment(nodes=frozenset([node1, node2]))
        expected = dict(
            dataset_id=expected_dataset.dataset_id,
            primary=expected_hostname,
            metadata=thaw(expected_dataset.metadata),
            deleted=False,
        )
        self.assertEqual(
            [expected], list(datasets_from_deployment(deployment)))

    def test_replica_manifestations_only(self):
        """
        ``datasets_from_deployment`` does not return datasets if there are only
        replica manifestations.
        """
        manifestation1 = Manifestation(
            dataset=Dataset(dataset_id=unicode(uuid4())),
            primary=False
        )
        manifestation2 = Manifestation(
            dataset=Dataset(dataset_id=unicode(uuid4())),
            primary=False
        )

        node1 = Node(
            hostname=u"node1.example.com",
            applications=frozenset(),
            manifestations={manifestation1.dataset_id:
                            manifestation1},
        )

        node2 = Node(
            hostname=u"node2.example.com",
            applications=frozenset(),
            manifestations={manifestation2.dataset_id:
                            manifestation2},
        )

        deployment = Deployment(nodes=frozenset([node1, node2]))

        self.assertEqual([], list(datasets_from_deployment(deployment)))

    def test_multiple_primary_manifestations(self):
        """
        ``datasets_from_deployment`` may return multiple primary datasets.
        """
        manifestation1 = Manifestation(
            dataset=Dataset(dataset_id=unicode(uuid4())),
            primary=True
        )
        manifestation2 = Manifestation(
            dataset=Dataset(dataset_id=unicode(uuid4())),
            primary=True
        )

        node1 = Node(
            hostname=u"node1.example.com",
            applications=frozenset(),
            manifestations={manifestation1.dataset_id:
                            manifestation1},
        )

        node2 = Node(
            hostname=u"node2.example.com",
            applications=frozenset(),
            manifestations={manifestation2.dataset_id:
                            manifestation2},
        )

        deployment = Deployment(nodes=frozenset([node1, node2]))
        self.assertEqual(
            set([manifestation1.dataset.dataset_id,
                 manifestation2.dataset.dataset_id]),
            set(d['dataset_id'] for d in datasets_from_deployment(deployment))
        )


class APIDatasetFromDatasetAndNodeTests(SynchronousTestCase):
    """
    Tests for ``api_dataset_from_dataset_and_node``.
    """
    def test_without_maximum_size(self):
        """
        ``maximum_size`` is omitted from the returned dict if the dataset
        maximum_size is None.
        """
        dataset = Dataset(dataset_id=unicode(uuid4()))
        expected_hostname = u'192.0.2.101'
        expected = dict(
            dataset_id=dataset.dataset_id,
            primary=expected_hostname,
            metadata={},
            deleted=False,
        )
        self.assertEqual(
            expected,
            api_dataset_from_dataset_and_node(dataset, expected_hostname)
        )

    def test_with_maximum_size(self):
        """
        ``maximum_size`` is included in the returned dict if the dataset
        maximum_size is set.
        """
        expected_size = 1024 * 1024 * 1024 * 42
        dataset = Dataset(
            dataset_id=unicode(uuid4()),
            maximum_size=expected_size,
        )
        expected_hostname = u'192.0.2.101'
        expected = dict(
            dataset_id=dataset.dataset_id,
            primary=expected_hostname,
            maximum_size=expected_size,
            metadata={},
            deleted=False,
        )
        self.assertEqual(
            expected,
            api_dataset_from_dataset_and_node(dataset, expected_hostname)
        )

    def test_deleted(self):
        """
        ``deleted`` key is set to True if the dataset is deleted.
        """
        dataset = Dataset(dataset_id=unicode(uuid4()), deleted=True)
        expected_hostname = u'192.0.2.101'
        expected = dict(
            dataset_id=dataset.dataset_id,
            primary=expected_hostname,
            metadata={},
            deleted=True,
        )
        self.assertEqual(
            expected,
            api_dataset_from_dataset_and_node(dataset, expected_hostname)
        )
