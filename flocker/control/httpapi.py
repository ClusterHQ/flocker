# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
"""
A HTTP REST API for controlling the Dataset Manager.
"""

import yaml
from uuid import uuid4

from pyrsistent import pmap

from twisted.python.filepath import FilePath
from twisted.web.http import CONFLICT, CREATED
from twisted.web.server import Site
from twisted.web.resource import Resource
from twisted.application.internet import StreamServerEndpointService

from klein import Klein

from ..restapi import (
    EndpointResponse, structured, user_documentation, make_bad_request
)
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

    The APIs exposed here typically operate on cluster configuration.  They
    frequently return success results when a configuration change has been made
    durable but has not yet been deployed onto the cluster.
    """
    app = Klein()

    def __init__(self, persistence_service, cluster_state_service):
        """
        :param ConfigurationPersistenceService persistence_service: Service
            for retrieving and setting desired configuration.

        :param ClusterStateService cluster_state_service: Service that
            knows about the current state of the cluster.
        """
        self.persistence_service = persistence_service
        self.cluster_state_service = cluster_state_service

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
    @user_documentation(
        """
        Create a new dataset.
        """,
        examples=[
            u"create dataset",
            u"create dataset with dataset_id",
            u"create dataset with duplicate dataset_id",
            u"create dataset with maximum_size",
            u"create dataset with metadata",
        ]
    )
    @structured(
        inputSchema={'$ref': '/v1/endpoints.json#/definitions/datasets'},
        outputSchema={'$ref': '/v1/endpoints.json#/definitions/datasets'},
        schema_store=SCHEMAS
    )
    def create_dataset(self, primary, dataset_id=None, maximum_size=None,
                       metadata=None):
        """
        Create a new dataset in the cluster configuration.

        :param unicode primary: The address of the node on which the primary
            manifestation of the dataset will be created.

        :param unicode dataset_id: A unique identifier to assign to the
            dataset.  This is a string giving a UUID (per RFC 4122).  If no
            value is given, one will be generated and returned in the response.
            This is not for easy human use.  For human-friendly identifiers,
            use items in ``metadata``.

        :param int maximum_size: The maximum number of bytes the dataset will
            be capable of storing.  This may be optional or required depending
            on the dataset backend.

        :param dict metadata: A small collection of unicode key/value pairs to
            associate with the dataset.  These items are not interpreted.  They
            are only stored and made available for later retrieval.  Use this
            for things like human-friendly dataset naming, ownership
            information, etc.

        :return: A ``dict`` describing the dataset which has been added to the
            cluster configuration or giving error information if this is not
            possible.
        """
        if dataset_id is None:
            dataset_id = unicode(uuid4())
        dataset_id = dataset_id.lower()

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
        # See FLOC-1278

        dataset = Dataset(
            dataset_id=dataset_id,
            maximum_size=maximum_size,
            metadata=pmap(metadata)
        )
        manifestation = Manifestation(dataset=dataset, primary=True)

        primary_nodes = list(
            node for node in deployment.nodes if primary == node.hostname
        )
        if len(primary_nodes) == 0:
            # The node wasn't found in the configuration so create a new node
            # to which a manifestation can be added.  FLOC-1278 will make sure
            # we're not creating nonsense configuration in this step.
            primary_node = Node(hostname=primary)
        else:
            # One was found.  Add the manifestation to it.
            (primary_node,) = primary_nodes

        new_node_config = Node(
            hostname=primary_node.hostname,
            applications=primary_node.applications,
            other_manifestations=(
                primary_node.other_manifestations | frozenset({manifestation})
            )
        )
        other_nodes = frozenset(
            node for node in deployment.nodes if node is not primary_node
        )
        new_deployment = Deployment(
            nodes=other_nodes | frozenset({new_node_config})
        )
        saving = self.persistence_service.save(new_deployment)

        def saved(ignored):
            result = {
                u"dataset_id": dataset_id,
                u"primary": primary,
                u"metadata": metadata,
            }
            if maximum_size is not None:
                result[u"maximum_size"] = maximum_size
            return EndpointResponse(CREATED, result)
        saving.addCallback(saved)
        return saving

    # # Will we also have a /state endpoint? Or just route directly to the datasets path?
    # @app.route("/state/datasets", methods=['GET'])
    # @user_documentation("""
    #     Get current cluster datasets
    #     """, examples=[u"get state datasets"])
    # @structured(
    #     inputSchema={},
    #     outputSchema={'$ref': '/v1/endpoints.json#/definitions/state/datasets'},
    #     schema_store=SCHEMAS
    # )
    # def datasets(self):
    #     """
    #     Return all datasets in the cluster.
    #     """
    #     deployment = self.cluster_state_service.as_deployment()
    #     # Filter out the datasets and their current nodes.
    #     return datasets_from_deployment(deployment)

# def datasets_from_deployment(deployment):
#     """
#     Return a dictionary of nodes and their datasets.
#     """

def create_api_service(persistence_service, cluster_state_service, endpoint):
    """
    Create a Twisted Service that serves the API on the given endpoint.

    :param ConfigurationPersistenceService persistence_service: Service
        for retrieving and setting desired configuration.

    :param ClusterStateService cluster_state_service: Service that
        knows about the current state of the cluster.

    :param endpoint: Twisted endpoint to listen on.

    :return: Service that will listen on the endpoint using HTTP API server.
    """
    api_root = Resource()
    user = DatasetAPIUserV1(persistence_service, cluster_state_service)
    api_root.putChild('v1', user.app.resource())
    api_root._v1_user = user  # For unit testing purposes, alas
    return StreamServerEndpointService(endpoint, Site(api_root))
