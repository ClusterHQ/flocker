# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
"""
A HTTP REST API for controlling the Dataset Manager.
"""

import yaml
from uuid import uuid4

from pyrsistent import pmap

from twisted.python.filepath import FilePath
from twisted.web.http import CONFLICT
from twisted.web.server import Site
from twisted.web.resource import Resource
from twisted.application.internet import StreamServerEndpointService

from klein import Klein

from ..restapi import structured, user_documentation, make_bad_request
from . import Dataset, Manifestation, Node, Deployment
from .. import __version__


SCHEMA_BASE = FilePath(__file__).parent().child(b'schema')
SCHEMAS = {
    b'/v1/types.json': yaml.safe_load(
        SCHEMA_BASE.child(b'types.yml').getContent()),
    b'/v1/endpoints.json': yaml.safe_load(
        SCHEMA_BASE.child(b'endpoints.yml').getContent()),
    }


DATASET_ID_COLLISION = make_bad_request(
    code=CONFLICT, description=u"The provided dataset_id is already in use.")
PRIMARY_NODE_NOT_FOUND = make_bad_request(
    description=u"The provided primary node is not part of the cluster.")


class DatasetAPIUserV1(object):
    """
    A user accessing the API.
    """
    app = Klein()

    def __init__(self, persistence_service):
        """
        :param ConfigurationPersistenceService persistence_service: Service
            for retrieving and setting desired configuration.
        """
        self.persistence_service = persistence_service

    @app.route("/version", methods=['GET'])
    @user_documentation("""
        Get the version of Flocker being run.
        """, examples=[u"get version"])
    @structured(
        inputSchema={},
        outputSchema={'$ref': '/v1/endpoints.json#/definitions/versions'},
        schema_store=SCHEMAS
    )
    def version(self):
        """
        Return the ``flocker`` version string.
        """
        return {u"flocker":  __version__}


    @app.route("/datasets", methods=['POST'])
    @user_documentation("""
        Create a new dataset.
        """, examples=[
            u"create dataset",
            u"create dataset with dataset_id",
            u"create dataset with duplicate dataset_id",
            u"create dataset with maximum_size",
            u"create dataset with metadata",
        ])
    @structured(
        inputSchema={'$ref': '/v1/endpoints.json#/definitions/datasets'},
        outputSchema={'$ref': '/v1/endpoints.json#/definitions/datasets'},
        schema_store=SCHEMAS
    )
    def create_dataset(self, primary, dataset_id=None, metadata=None):
        """
        Create a new dataset on the cluster.
        """
        if dataset_id is None:
            dataset_id = u"x" * 36 # unicode(uuid4())

        if metadata is None:
            metadata = {}

        # Use persistence_service to get a Deployment for the cluster
        # configuration.
        deployment = self.persistence_service.get()
        for node in deployment.nodes:
            for manifestation in node.manifestations():
                if manifestation.dataset.dataset_id == dataset_id:
                    raise DATASET_ID_COLLISION

        # XXX Check cluster state to determine if the given primary node
        # actually exists.  If not, raise PRIMARY_NODE_NOT_FOUND.

        dataset = Dataset(dataset_id=dataset_id, metadata=pmap(metadata))
        manifestation = Manifestation(dataset=dataset, primary=True)

        primary_nodes = list(
            node for node in deployment.nodes if primary == node.hostname
        )
        if len(primary_nodes) == 0:
            primary_node = Node(hostname=primary)
        else:
            (primary_node,) = primary_nodes

        new_node_config = Node(
            hostname=primary_node.hostname,
            applications=primary_node.applications,
            other_manifestations=
                primary_node.other_manifestations | frozenset({manifestation})
        )
        new_deployment = Deployment(
            nodes=frozenset(
                node for node in deployment.nodes if node is not primary_node
            ) | frozenset({new_node_config})
        )

        saving = self.persistence_service.save(new_deployment)
        def saved(ignored):
            return {
                u"dataset_id": dataset_id,
                u"primary": primary,
                u"metadata": metadata,
            }
        saving.addCallback(saved)
        return saving


def create_api_service(persistence_service, endpoint):
    """
    Create a Twisted Service that serves the API on the given endpoint.

    :param ConfigurationPersistenceService persistence_service: Service
        for retrieving and setting desired configuration.
    :param endpoint: Twisted endpoint to listen on.

    :return: Service that will listen on the endpoint using HTTP API server.
    """
    api_root = Resource()
    api_root.putChild(
        'v1', DatasetAPIUserV1(persistence_service).app.resource())
    return StreamServerEndpointService(endpoint, Site(api_root))
