# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
"""
A HTTP REST API for controlling the Dataset Manager.
"""

import yaml
from uuid import uuid4

from pyrsistent import pmap, thaw

from twisted.python.filepath import FilePath
from twisted.web.http import CONFLICT, CREATED, NOT_FOUND, OK
from twisted.web.server import Site
from twisted.web.resource import Resource
from twisted.application.internet import StreamServerEndpointService

from klein import Klein

from ..restapi import (
    EndpointResponse, structured, user_documentation, make_bad_request
)
from . import Dataset, Manifestation, Node, Deployment
from .. import __version__


# Default port for REST API:
REST_API_PORT = 4523


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
DATASET_NOT_FOUND = make_bad_request(
    code=NOT_FOUND, description=u"Dataset not found.")


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

    @app.route("/configuration/datasets", methods=['GET'])
    @user_documentation(
        """
        Get the cluster's dataset configuration.
        """,
        examples=[u"get configured datasets"],
    )
    @structured(
        inputSchema={},
        outputSchema={
            '$ref': '/v1/endpoints.json#/definitions/datasets_array',
        },
        schema_store=SCHEMAS,
    )
    def get_dataset_configuration(self):
        """
        Get the configured datasets.

        :return: A ``list`` of ``dict`` representing each of dataset
            that is configured to exist anywhere on the cluster.
        """
        return list(datasets_from_deployment(self.persistence_service.get()))

    @app.route("/configuration/datasets", methods=['POST'])
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
    def create_dataset_configuration(self, primary, dataset_id=None,
                                     maximum_size=None, metadata=None):
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

    @app.route("/configuration/datasets/<dataset_id>", methods=['POST'])
    @user_documentation(
        """
        Update an existing dataset.
        """,
        examples=[
            u"update dataset with primary",
            u"update dataset with unknown dataset id",
        ]
    )
    @structured(
        inputSchema={'$ref': '/v1/endpoints.json#/definitions/datasets'},
        outputSchema={'$ref': '/v1/endpoints.json#/definitions/datasets'},
        schema_store=SCHEMAS
    )
    def update_dataset(self, dataset_id, primary=None):
        """
        Update an existing dataset in the cluster configuration.

        :param unicode dataset_id: The unique identifier of the dataset.  This
            is a string giving a UUID (per RFC 4122).

        :param unicode primary: The address of the node to which the dataset
            will be moved.

        :return: A ``dict`` describing the dataset which has been added to the
            cluster configuration or giving error information if this is not
            possible.
        """
        # Get the current configuration.
        deployment = self.persistence_service.get()

        # Lookup the node that has a primary Manifestation (if any)
        manifestations_and_nodes = other_manifestations_from_deployment(
            deployment, dataset_id)
        index = 0
        for index, (manifestation, node) in enumerate(
                manifestations_and_nodes):
            if manifestation.primary:
                primary_manifestation, origin_node = manifestation, node
                break
        else:
            # There are no manifestations containing the requested dataset.
            if index == 0:
                raise DATASET_NOT_FOUND
            else:
                # There were no primary manifestations
                raise IndexError(
                    'No primary manifestations for dataset: {!r}. See '
                    'https://clusterhq.atlassian.net/browse/FLOC-1403'.format(
                        dataset_id)
                )

        # Now construct a new_deployment where the primary manifestation of the
        # dataset is on the requested primary node.
        new_origin_node = Node(
            hostname=origin_node.hostname,
            applications=origin_node.applications,
            other_manifestations=(
                origin_node.other_manifestations
                - frozenset({primary_manifestation})
            )
        )
        deployment = deployment.update_node(new_origin_node)

        primary_nodes = list(
            node for node in deployment.nodes if primary == node.hostname
        )
        if len(primary_nodes) == 0:
            # `primary` is not in cluster. Add it.
            # XXX Check cluster state to determine if the given primary node
            # actually exists.  If not, raise PRIMARY_NODE_NOT_FOUND.
            # See FLOC-1278
            new_target_node = Node(
                hostname=primary,
                other_manifestations=frozenset({primary_manifestation})
            )
        else:
            # There should only be one node with the requested primary
            # hostname. ``ValueError`` here if that's not the case.
            (target_node,) = primary_nodes
            new_target_node = Node(
                hostname=target_node.hostname,
                applications=target_node.applications,
                other_manifestations=(
                    target_node.other_manifestations
                    | frozenset({primary_manifestation})
                )
            )

        deployment = deployment.update_node(new_target_node)

        saving = self.persistence_service.save(deployment)

        # Return an API response dictionary containing the dataset with updated
        # primary address.
        def saved(ignored):
            result = api_dataset_from_dataset_and_node(
                primary_manifestation.dataset,
                new_target_node.hostname
            )
            return EndpointResponse(OK, result)
        saving.addCallback(saved)
        return saving

    @app.route("/state/datasets", methods=['GET'])
    @user_documentation("""
        Get current cluster datasets.
        """, examples=[u"get state datasets"])
    @structured(
        inputSchema={},
        outputSchema={
            '$ref': '/v1/endpoints.json#/definitions/datasets_array'
            },
        schema_store=SCHEMAS
    )
    def state_datasets(self):
        """
        Return the current primary datasets in the cluster.

        :return: A ``list`` containing all datasets in the cluster.
        """
        deployment = self.cluster_state_service.as_deployment()
        return list(datasets_from_deployment(deployment))


def other_manifestations_from_deployment(deployment, dataset_id):
    """
    Extract all other manifestations of the supplied dataset_id from the
    supplied deployment.

    :param Deployment deployment: A ``Deployment`` describing the state
        of the cluster.
    :param unicode dataset_id: The uuid of the ``Dataset`` for the
        ``Manifestation`` s that are to be returned.
    :return: Iterable returning all manifestations of the supplied
        ``dataset_id``.
    """
    for node in deployment.nodes:
        for manifestation in node.other_manifestations:
            if manifestation.dataset.dataset_id == dataset_id:
                yield manifestation, node


def datasets_from_deployment(deployment):
    """
    Extract the primary datasets from the supplied deployment instance.

    Currently does not support secondary datasets, but this info might be
    useful to provide.  For ZFS, for example, may show how up-to-date they
    are with respect to the primary.

    :param Deployment deployment: A ``Deployment`` describing the state
        of the cluster.

    :return: Iterable returning all datasets.
    """
    for node in deployment.nodes:
        for manifestation in node.manifestations():
            if manifestation.primary:
                # There may be multiple datasets marked as primary until we
                # implement consistency checking when state is reported by each
                # node.
                # See https://clusterhq.atlassian.net/browse/FLOC-1303
                yield api_dataset_from_dataset_and_node(
                    manifestation.dataset, node.hostname
                )


def api_dataset_from_dataset_and_node(dataset, node_hostname):
    """
    Return a dataset dict which conforms to
    ``/v1/endpoints.json#/definitions/datasets_array``

    :param Dataset dataset: A dataset present in the cluster.
    :param unicode node_hostname: Hostname of the primary node for the
        `dataset`.
    :return: A ``dict`` containing the dataset information and the
        hostname of the primary node, conforming to
        ``/v1/endpoints.json#/definitions/datasets_array``.
    """
    result = dict(
        dataset_id=dataset.dataset_id,
        primary=node_hostname,
        metadata=thaw(dataset.metadata)
    )
    if dataset.maximum_size is not None:
        result[u'maximum_size'] = dataset.maximum_size
    return result


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
