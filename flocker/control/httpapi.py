# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
"""
A HTTP REST API for controlling the Dataset Manager.
"""

import yaml
from uuid import uuid4

from pyrsistent import pmap, thaw

from twisted.python.filepath import FilePath
from twisted.web.http import (
    CONFLICT, CREATED, NOT_FOUND, OK, NOT_ALLOWED as METHOD_NOT_ALLOWED,
)
from twisted.web.server import Site
from twisted.web.resource import Resource
from twisted.application.internet import StreamServerEndpointService

from klein import Klein

from pyrsistent import discard

from ..restapi import (
    EndpointResponse, structured, user_documentation, make_bad_request
)
from . import (
    Dataset, Manifestation, Node, Application, DockerImage, Port
)
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

CONTAINER_NAME_COLLISION = make_bad_request(
    code=CONFLICT, description=u"The container name already exists."
)
CONTAINER_NOT_FOUND = make_bad_request(
    code=NOT_FOUND, description=u"Container not found.")
CONTAINER_PORT_COLLISION = make_bad_request(
    code=CONFLICT, description=u"A specified external port is already in use."
)
DATASET_ID_COLLISION = make_bad_request(
    code=CONFLICT, description=u"The provided dataset_id is already in use.")
PRIMARY_NODE_NOT_FOUND = make_bad_request(
    description=u"The provided primary node is not part of the cluster.")
DATASET_NOT_FOUND = make_bad_request(
    code=NOT_FOUND, description=u"Dataset not found.")
DATASET_DELETED = make_bad_request(
    code=METHOD_NOT_ALLOWED, description=u"The dataset has been deleted.")


class ConfigurationAPIUserV1(object):
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

    def _find_node_by_host(self, host, deployment):
        """
        Find a Node matching the specified host, or create a new one if it does
        not already exist.
        :param node: A ``unicode`` representing a host / IP address.
        :param deployment: A ``Deployment`` instance.
        :return: A ``Node`` instance.
        """
        for node in deployment.nodes:
            if host == node.hostname:
                return node

        # The node wasn't found in the configuration so create a new node.
        # FLOC-1278 will make sure we're not creating nonsense
        # configuration in this step.
        return Node(hostname=host)

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
            '$ref':
            '/v1/endpoints.json#/definitions/configuration_datasets_array',
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
        inputSchema={'$ref':
                     '/v1/endpoints.json#/definitions/configuration_dataset'},
        outputSchema={'$ref':
                      '/v1/endpoints.json#/definitions/configuration_dataset'},
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
            for manifestation in node.manifestations.values():
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

        primary_node = self._find_node_by_host(primary, deployment)

        new_node_config = primary_node.transform(
            ("manifestations", manifestation.dataset_id), manifestation)
        new_deployment = deployment.update_node(new_node_config)
        saving = self.persistence_service.save(new_deployment)

        def saved(ignored):
            result = api_dataset_from_dataset_and_node(dataset, primary)
            return EndpointResponse(CREATED, result)
        saving.addCallback(saved)
        return saving

    def _find_manifestation_and_node(self, dataset_id):
        """
        Given the ID of a dataset, find its primary manifestation and the node
        it's on.

        :param unicode dataset_id: The unique identifier of the dataset.  This
            is a string giving a UUID (per RFC 4122).

        :return: Tuple containing the primary ``Manifestation`` and the
            ``Node`` it is on.
        """
        # Get the current configuration.
        deployment = self.persistence_service.get()

        manifestations_and_nodes = manifestations_from_deployment(
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

        return primary_manifestation, origin_node

    @app.route("/configuration/datasets/<dataset_id>", methods=['DELETE'])
    @user_documentation(
        """
        Delete an existing dataset.

        Deletion is idempotent: deleting a dataset multiple times will
        result in the same response.
        """,
        examples=[
            u"delete dataset",
            u"delete dataset with unknown dataset id",
        ]
    )
    @structured(
        inputSchema={},
        outputSchema={'$ref':
                      '/v1/endpoints.json#/definitions/configuration_dataset'},
        schema_store=SCHEMAS
    )
    def delete_dataset(self, dataset_id):
        """
        Delete an existing dataset in the cluster configuration.

       :param unicode dataset_id: The unique identifier of the dataset.  This
            is a string giving a UUID (per RFC 4122).

        :return: A ``dict`` describing the dataset which has been marked
            as deleted in the cluster configuration or giving error
            information if this is not possible.
        """
        # Get the current configuration.
        deployment = self.persistence_service.get()

        # XXX this doesn't handle replicas
        # https://clusterhq.atlassian.net/browse/FLOC-1240
        old_manifestation, origin_node = self._find_manifestation_and_node(
            dataset_id)

        new_node = origin_node.transform(
            ("manifestations", dataset_id, "dataset", "deleted"), True)
        deployment = deployment.update_node(new_node)

        saving = self.persistence_service.save(deployment)

        def saved(ignored):
            result = api_dataset_from_dataset_and_node(
                new_node.manifestations[dataset_id].dataset, new_node.hostname,
            )
            return EndpointResponse(OK, result)
        saving.addCallback(saved)
        return saving

    @app.route("/configuration/datasets/<dataset_id>", methods=['POST'])
    @user_documentation(
        """
        Update an existing dataset.

        This can be used to:

        * Move a dataset from one node to another by changing the
          ``primary`` attribute.
        * In the future, update metadata and maximum size.

        """,
        examples=[
            u"update dataset with primary",
            u"update dataset with unknown dataset id",
        ]
    )
    @structured(
        inputSchema={'$ref':
                     '/v1/endpoints.json#/definitions/configuration_dataset'},
        outputSchema={'$ref':
                      '/v1/endpoints.json#/definitions/configuration_dataset'},
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

        primary_manifestation, origin_node = self._find_manifestation_and_node(
            dataset_id)

        if primary_manifestation.dataset.deleted:
            raise DATASET_DELETED

        # Now construct a new_deployment where the primary manifestation of the
        # dataset is on the requested primary node.
        new_origin_node = origin_node.transform(
            ("manifestations", dataset_id), discard)
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
                manifestations={dataset_id: primary_manifestation},
            )
        else:
            # There should only be one node with the requested primary
            # hostname. ``ValueError`` here if that's not the case.
            (target_node,) = primary_nodes
            new_target_node = target_node.transform(
                ("manifestations", dataset_id), primary_manifestation)

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
            '$ref': '/v1/endpoints.json#/definitions/state_datasets_array'
            },
        schema_store=SCHEMAS
    )
    def state_datasets(self):
        """
        Return the current primary datasets in the cluster.

        :return: A ``list`` containing all datasets in the cluster.
        """
        deployment = self.cluster_state_service.as_deployment()
        datasets = list(datasets_from_deployment(deployment))
        for dataset in datasets:
            dataset[u"path"] = self.cluster_state_service.manifestation_path(
                dataset[u"primary"], dataset[u"dataset_id"]).path.decode(
                    "utf-8")
            del dataset[u"metadata"]
            del dataset[u"deleted"]
        return datasets

    @app.route("/configuration/containers", methods=['POST'])
    @user_documentation(
        """
        Add a new container to the configuration.

        The container will be automatically started once it is created on
        the cluster.
        """,
        examples=[
            u"create container",
            u"create container with duplicate name",
            u"create container with ports",
            u"create container with environment",
        ]
    )
    @structured(
        inputSchema={
            '$ref': '/v1/endpoints.json#/definitions/configuration_container'},
        outputSchema={
            '$ref': '/v1/endpoints.json#/definitions/configuration_container'},
        schema_store=SCHEMAS
    )
    def create_container_configuration(
        self, host, name, image, ports=(), environment=None
    ):
        """
        Create a new dataset in the cluster configuration.

        :param unicode host: The address of the node on which the container
            will run.

        :param unicode name: A unique identifier for the container within
            the Flocker cluster.

        :param unicode image: The name of the Docker image to use for the
            container.

        :param list ports: A ``list`` of ``dict`` objects, mapping internal
            to external ports for the container.

        :param dict environment: A ``dict`` of key/value pairs to be supplied
            to the container as environment variables. Keys and values must be
            ``unicode``.

        :return: An ``EndpointResponse`` describing the container which has
            been added to the cluster configuration.
        """
        deployment = self.persistence_service.get()

        # Check if container by this name already exists, if it does
        # return error.

        for node in deployment.nodes:
            for application in node.applications:
                if application.name == name:
                    raise CONTAINER_NAME_COLLISION

        # Find the node.
        node = self._find_node_by_host(host, deployment)

        # Check if we have any ports in the request. If we do, check existing
        # external ports exposed to ensure there is no conflict. If there is a
        # conflict, return an error.

        for port in ports:
            for current_node in deployment.nodes:
                for application in current_node.applications:
                    for application_port in application.ports:
                        if application_port.external_port == port['external']:
                            raise CONTAINER_PORT_COLLISION

        # If we have ports specified, add these to the Application instance.
        application_ports = []
        for port in ports:
            application_ports.append(Port(
                internal_port=port['internal'],
                external_port=port['external']
            ))

        if environment is not None:
            environment = frozenset(environment.items())

        # Create Application object, add to Deployment, save.
        application = Application(
            name=name,
            image=DockerImage.from_string(image),
            ports=frozenset(application_ports),
            environment=environment
        )

        new_node_config = node.transform(
            ["applications"],
            lambda s: s.add(application)
        )

        new_deployment = deployment.update_node(new_node_config)
        saving = self.persistence_service.save(new_deployment)

        # Return passed in dictionary with CREATED response code.
        def saved(_):
            result = container_configuration_response(application, host)
            return EndpointResponse(CREATED, result)
        saving.addCallback(saved)
        return saving

    @app.route("/configuration/containers/<name>", methods=['DELETE'])
    @user_documentation(
        """
        Remove a container from the configuration.

        This will lead to the container being stopped and not being
        restarted again.
        """,
        examples=[
            u"remove a container",
            u"remove a container with unknown name",
        ]
    )
    @structured(
        inputSchema={},
        outputSchema={},
        schema_store=SCHEMAS
    )
    def delete_container_configuration(self, name):
        """
        Remove a container from the cluster configuration.

        :param unicode name: A unique identifier for the container within
            the Flocker cluster.

        :return: An ``EndpointResponse``.
        """
        deployment = self.persistence_service.get()

        for node in deployment.nodes:
            for application in node.applications:
                if application.name == name:
                    updated_node = node.transform(
                        ["applications"], lambda s: s.remove(application))
                    d = self.persistence_service.save(
                        deployment.update_node(updated_node))
                    d.addCallback(lambda _: None)
                    return d

        # Didn't find the application:
        raise CONTAINER_NOT_FOUND


def manifestations_from_deployment(deployment, dataset_id):
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
        if dataset_id in node.manifestations:
                yield node.manifestations[dataset_id], node


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
        for manifestation in node.manifestations.values():
            if manifestation.primary:
                # There may be multiple datasets marked as primary until we
                # implement consistency checking when state is reported by each
                # node.
                # See https://clusterhq.atlassian.net/browse/FLOC-1303
                yield api_dataset_from_dataset_and_node(
                    manifestation.dataset, node.hostname
                )


def container_configuration_response(application, node):
    """
    Return a container dict  which confirms to
    ``/v1/endpoints.json#/definitions/configuration_container``

    :param Application application: An ``Application`` instance.
    :param unicode node: The host on which this application is running.
    :return: A ``dict`` containing the container configuration.
    """
    result = {
        "host": node, "name": application.name,
        "image": application.image.full_name,
    }
    if application.ports:
        result['ports'] = []
        for port in application.ports:
            result['ports'].append(dict(
                internal=port.internal_port, external=port.external_port
            ))
    if application.environment:
        result['environment'] = dict(application.environment)
    return result


def api_dataset_from_dataset_and_node(dataset, node_hostname):
    """
    Return a dataset dict which conforms to
    ``/v1/endpoints.json#/definitions/configuration_datasets_array``

    :param Dataset dataset: A dataset present in the cluster.
    :param unicode node_hostname: Hostname of the primary node for the
        `dataset`.
    :return: A ``dict`` containing the dataset information and the
        hostname of the primary node, conforming to
        ``/v1/endpoints.json#/definitions/configuration_datasets_array``.
    """
    result = dict(
        dataset_id=dataset.dataset_id,
        deleted=dataset.deleted,
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
    user = ConfigurationAPIUserV1(persistence_service, cluster_state_service)
    api_root.putChild('v1', user.app.resource())
    api_root._v1_user = user  # For unit testing purposes, alas
    return StreamServerEndpointService(endpoint, Site(api_root))
