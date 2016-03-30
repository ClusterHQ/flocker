# Copyright ClusterHQ Inc.  See LICENSE file for details.
"""
A HTTP REST API for controlling the Dataset Manager.
"""

from uuid import uuid4, UUID
from datetime import datetime
from functools import wraps
from json import dumps

from pytz import UTC

import yaml

from pyrsistent import pmap, thaw

from twisted.protocols.tls import TLSMemoryBIOFactory

from twisted.python.filepath import FilePath
from twisted.web.http import (
    CONFLICT, CREATED, NOT_FOUND, OK, NOT_ALLOWED as METHOD_NOT_ALLOWED,
    BAD_REQUEST, PRECONDITION_FAILED,
)
from twisted.web.server import Site
from twisted.web.resource import Resource
from twisted.application.internet import StreamServerEndpointService
from twisted.internet import reactor

from klein import Klein

from pyrsistent import discard

from repoze.lru import lru_cache

from ..restapi import (
    EndpointResponse, structured, user_documentation, make_bad_request,
    private_api
)
from . import (
    Dataset, Manifestation, Application, DockerImage, Port,
    AttachedVolume, Link
)
from ._config import (
    ApplicationMarshaller, FLOCKER_RESTART_POLICY_NAME_TO_POLICY,
    model_from_configuration, FigConfiguration, FlockerConfiguration,
    ConfigurationError
)
from ._persistence import update_leases
from ._model import LeaseError

from .. import __version__, REST_API_PORT as _port
REST_API_PORT = _port  # Some modules expect this constant to be here


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
LINK_PORT_COLLISION = make_bad_request(
    code=CONFLICT,
    description=u"The local ports in a container's links must be unique."
)
LINK_ALIAS_COLLISION = make_bad_request(
    code=CONFLICT, description=u"Link aliases must be unique."
)
DATASET_ID_COLLISION = make_bad_request(
    code=CONFLICT, description=u"The provided dataset_id is already in use.")
PRIMARY_NODE_NOT_FOUND = make_bad_request(
    description=u"The provided primary node is not part of the cluster.")
DATASET_NOT_FOUND = make_bad_request(
    code=NOT_FOUND, description=u"Dataset not found.")
DATASET_DELETED = make_bad_request(
    code=METHOD_NOT_ALLOWED, description=u"The dataset has been deleted.")
DATASET_ON_DIFFERENT_NODE = make_bad_request(
    code=CONFLICT, description=u"The dataset is on another node.")
DATASET_IN_USE = make_bad_request(
    code=CONFLICT,
    description=u"The dataset is being used by another container.")
LEASE_NOT_FOUND = make_bad_request(
    code=NOT_FOUND, description=u"Lease not found.")
LEASE_HELD = make_bad_request(
    code=CONFLICT, description=u"Lease already held.")
NODE_BY_ERA_NOT_FOUND = make_bad_request(
    code=NOT_FOUND, description=u"No node found with given era.")

_UNDEFINED_MAXIMUM_SIZE = object()

IF_MATCHES_HEADER = b"X-If-Configuration-Matches"


def get_configuration_tag(api):
    """
    Return tag value for the configuration.

    :param ConfigurationAPIUserV1 api: API instance.
    :return: Tag as ``bytes``.
    """
    return api.persistence_service.configuration_hash()


def _if_configuration_matches(original):
    """
    Decorator that compares ``X-If-Configuration-Matches`` header to result of
    ``get_configuration_tag``.

    :param original: Original function.
    :return: Wrapped function.
    """
    @wraps(original)
    def render_if_matches(self, request, **route_arguments):
        if request.requestHeaders.hasHeader(IF_MATCHES_HEADER):
            tag = get_configuration_tag(self)
            if_matches = request.requestHeaders.getRawHeaders(
                IF_MATCHES_HEADER)
            if tag not in if_matches:
                request.setResponseCode(PRECONDITION_FAILED)
                request.responseHeaders.setRawHeaders(
                    b"content-type", [b"application/json"])
                return dumps({"description":
                              "Tag doesn't match. Required: %s, current: %s"
                              % (if_matches[0], tag)})
        return original(self, request, **route_arguments)

    return render_if_matches


@lru_cache(1)
def _extract_containers_state(deployment_state):
    """
    Turn the deployment state into serializable simple types for every
    container in the deployment state.

    N.B.: Callers of this function should not mutate the returned value as this
    function uses an lru_cache.

    :param DeploymentState deployment_state: The deployment state to extract
        the containers from.

    :returns: The states of the containers in simple types.
    """
    result = []
    for node in deployment_state.nodes:
        if node.applications is None:
            continue
        for application in node.applications:
            container = container_configuration_response(
                application, node.uuid)
            container[u"running"] = application.running
            result.append(container)
    return result


class ConfigurationAPIUserV1(object):
    """
    A user accessing the API.

    The APIs exposed here typically operate on cluster configuration.  They
    frequently return success results when a configuration change has been made
    durable but has not yet been deployed onto the cluster.
    """
    app = Klein()

    def __init__(self, persistence_service, cluster_state_service,
                 clock=reactor):
        """
        :param ConfigurationPersistenceService persistence_service: Service
            for retrieving and setting desired configuration.

        :param ClusterStateService cluster_state_service: Service that
            knows about the current state of the cluster.

        :param IReactorTime clock: The clock to use for time. By default
            global reactor.
        """
        self.persistence_service = persistence_service
        self.cluster_state_service = cluster_state_service
        self.clock = clock

    @app.route("/version", methods=['GET'])
    @user_documentation(
        u"""
        Get the version of Flocker being run.
        """,
        section=u"common",
        header=u"Get Flocker version",
        examples=[u"get version"])
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
        u"""
        Get the cluster's dataset configuration.

        Includes a ``X-Configuration-Tag`` header in the response for use
        with operations that support ``X-If-Configuration-Matches``.
        """,
        header=u"Get the cluster's dataset configuration",
        examples=[u"get configured datasets"],
        section=u"dataset",
    )
    @structured(
        inputSchema={},
        outputSchema={
            '$ref':
            '/v1/endpoints.json#/definitions/configuration_datasets_list',
        },
        schema_store=SCHEMAS,
    )
    def get_dataset_configuration(self):
        """
        Get the configured datasets.

        :return: A ``list`` of ``dict`` representing each of dataset
            that is configured to exist anywhere on the cluster.
        """
        tag = get_configuration_tag(self)
        return EndpointResponse(
            OK, list(datasets_from_deployment(self.persistence_service.get())),
            headers={b"X-Configuration-Tag": tag})

    @app.route("/configuration/datasets", methods=['POST'])
    @user_documentation(
        u"""
        Create a new dataset.

        Supports ``X-If-Configuration-Matches`` header in the request to
        ensure creation only happens if the configuration hasn't changed.
        """,
        header=u"Create new dataset",
        examples=[
            u"create dataset",
            u"create dataset with dataset_id",
            u"create dataset with duplicate dataset_id",
            u"create dataset with maximum_size",
            u"create dataset with metadata",
        ],
        section=u"dataset",
    )
    @_if_configuration_matches
    @structured(
        inputSchema={
            '$ref':
            '/v1/endpoints.json#/definitions/configuration_datasets_create'
        },
        outputSchema={
            '$ref':
            '/v1/endpoints.json#/definitions/configuration_datasets'},
        schema_store=SCHEMAS,
    )
    def create_dataset_configuration(self, primary, dataset_id=None,
                                     maximum_size=None, metadata=None):
        """
        Create a new dataset in the cluster configuration.

        :param unicode primary: The UUID of the node on which the primary
            manifestation of the dataset will be created.

        :param unicode dataset_id: A unique identifier to assign to the
            dataset.  This is a string giving a UUID (per RFC 4122).  If no
            value is given, one will be generated and returned in the response.
            This is not for easy human use.  For human-friendly identifiers,
            use items in ``metadata``.

        :param maximum_size: Either the maximum number of bytes the dataset
            will be capable of storing or ``None`` to make the dataset size
            unlimited. This may be optional or required depending on the
            dataset backend.

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

        primary = UUID(hex=primary)

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

        primary_node = deployment.get_node(primary)

        new_node_config = primary_node.transform(
            ("manifestations", manifestation.dataset_id), manifestation)
        new_deployment = deployment.update_node(new_node_config)
        saving = self.persistence_service.save(new_deployment)

        def saved(ignored):
            result = api_dataset_from_dataset_and_node(dataset, primary)
            return EndpointResponse(CREATED, result)
        saving.addCallback(saved)
        return saving

    @app.route("/configuration/datasets/<dataset_id>", methods=['DELETE'])
    @user_documentation(
        u"""
        Deletion is idempotent: deleting a dataset multiple times will
        result in the same response.

        Supports ``X-If-Configuration-Matches`` header in the request to
        ensure deletion only happens if the configuration hasn't changed.
        """,
        header=u"Delete an existing dataset",
        examples=[
            u"delete dataset",
            u"delete dataset with unknown dataset id",
        ],
        section=u"dataset",
    )
    @_if_configuration_matches
    @structured(
        inputSchema={},
        outputSchema={
            '$ref':
            '/v1/endpoints.json#/definitions/configuration_datasets'},
        schema_store=SCHEMAS,
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
        _, origin_node = _find_manifestation_and_node(
            deployment, dataset_id)

        new_node = origin_node.transform(
            ("manifestations", dataset_id, "dataset", "deleted"), True)
        deployment = deployment.update_node(new_node)

        saving = self.persistence_service.save(deployment)

        def saved(ignored):
            result = api_dataset_from_dataset_and_node(
                new_node.manifestations[dataset_id].dataset, new_node.uuid,
            )
            return EndpointResponse(OK, result)
        saving.addCallback(saved)
        return saving

    @app.route("/configuration/datasets/<dataset_id>", methods=['POST'])
    @user_documentation(
        u"""
        This can be used to:

        * Move a dataset from one node to another by changing the
          ``primary`` attribute.
        * In the future this may be used to update metadata, but that is not
          currently supported.

        Supports ``X-If-Configuration-Matches`` header in the request to
        ensure the update only happens if the configuration hasn't
        changed.
        """,
        header=u"Update an existing dataset",
        examples=[
            u"update dataset with primary",
            u"update dataset with unknown dataset id",
        ],
        section=u"dataset",
    )
    @_if_configuration_matches
    @structured(
        inputSchema={
            '$ref':
            '/v1/endpoints.json#/definitions/configuration_datasets_update'},
        outputSchema={
            '$ref':
            '/v1/endpoints.json#/definitions/configuration_datasets'},
        schema_store=SCHEMAS,
    )
    def update_dataset(self, dataset_id, primary=None):
        """
        Update an existing dataset in the cluster configuration.

        :param unicode dataset_id: The unique identifier of the dataset.  This
            is a string giving a UUID (per RFC 4122).

        :param primary: The UUID of the node to which the dataset will be
            moved, or ``None`` indicating no change.

        :return: A ``dict`` describing the dataset which has been added to the
            cluster configuration or giving error information if this is not
            possible.
        """
        # Get the current configuration.
        deployment = self.persistence_service.get()

        # Raises DATASET_NOT_FOUND if the ``dataset_id`` is not found.
        primary_manifestation, current_node = _find_manifestation_and_node(
            deployment, dataset_id
        )

        if primary_manifestation.dataset.deleted:
            raise DATASET_DELETED

        if primary is not None:
            deployment = _update_dataset_primary(
                deployment, dataset_id, UUID(hex=primary)
            )

        saving = self.persistence_service.save(deployment)

        primary_manifestation, current_node = _find_manifestation_and_node(
            deployment, dataset_id
        )

        # Return an API response dictionary containing the dataset with updated
        # primary address.
        def saved(ignored):
            result = api_dataset_from_dataset_and_node(
                primary_manifestation.dataset,
                current_node.uuid,
            )
            return EndpointResponse(OK, result)
        saving.addCallback(saved)
        return saving

    @app.route("/state/datasets", methods=['GET'])
    @user_documentation(
        u"""
        The result reflects the control service's knowledge, which may be
        out of date or incomplete. E.g. a dataset agent has not connected
        or updated the control service yet.
        """,
        header=u"Get current cluster datasets",
        examples=[u"get state datasets"],
        section=u"dataset",
    )
    @structured(
        inputSchema={},
        outputSchema={
            '$ref': '/v1/endpoints.json#/definitions/state_datasets_array'
            },
        schema_store=SCHEMAS
    )
    def state_datasets(self):
        """
        Return all primary manifest datasets and all non-manifest datasets in
        the cluster.

        :return: A ``list`` containing all datasets in the cluster.
        """
        # XXX This duplicates code in datasets_from_deployment, but that
        # function is designed to operate on a Deployment rather than a
        # DeploymentState instance and the dataset configuration result
        # includes metadata and deleted flags which should not be part of the
        # dataset state response.
        # Refactor. See FLOC-2207.
        response = []
        deployment_state = self.cluster_state_service.as_deployment()
        get_manifestation_path = self.cluster_state_service.manifestation_path

        for dataset, node in deployment_state.all_datasets():
            response_dataset = dict(
                dataset_id=dataset.dataset_id,
            )

            if node is not None:
                response_dataset[u"primary"] = unicode(node.uuid)
                response_dataset[u"path"] = get_manifestation_path(
                    node.uuid,
                    dataset.dataset_id
                ).path.decode("utf-8")

            if dataset.maximum_size is not None:
                response_dataset[u"maximum_size"] = dataset.maximum_size

            response.append(response_dataset)
        return response

    @app.route("/configuration/containers", methods=['GET'])
    @user_documentation(
        u"""
        These containers may or may not actually exist on the
        cluster.
        """,
        header=u"Get the cluster's container configuration",
        examples=[u"get configured containers"],
        section=u"container",
    )
    @structured(
        inputSchema={},
        outputSchema={
            '$ref':
            '/v1/endpoints.json#/definitions/configuration_containers_array',
        },
        schema_store=SCHEMAS,
    )
    def get_containers_configuration(self):
        """
        Get the configured containers.

        :return: A ``list`` of ``dict`` representing each of the containers
            that are configured to exist anywhere on the cluster.
        """
        return list(
            _containers_from_deployment(self.persistence_service.get()))

    @app.route("/state/containers", methods=['GET'])
    @user_documentation(
        u"""
        This reflects the control service's knowledge of the cluster,
        which may be out of date or incomplete, e.g. if a container agent
        has not connected or updated the control service yet.
        """,
        header=u"Get the cluster's actual containers",
        examples=[u"get actual containers"],
        section=u"container",
    )
    @structured(
        inputSchema={},
        outputSchema={
            '$ref':
            '/v1/endpoints.json#/definitions/state_containers_array',
        },
        schema_store=SCHEMAS,
    )
    def get_containers_state(self):
        """
        Get the containers present in the cluster.

        :return: A ``list`` of ``dict`` representing each of the containers
            that are configured to exist anywhere on the cluster.
        """
        deployment_state = self.cluster_state_service.as_deployment()
        return _extract_containers_state(deployment_state)

    def _get_attached_volume(self, node_uuid, volume):
        """
        Create an ``AttachedVolume`` given a volume dictionary.

        :param UUID node_uuid: The node where the volume should be.
        :param dict volume: Parameters for specific volume passed to creation
            endpoint.

        :return AttachedVolume: Corresponding instance.
        """
        deployment = self.persistence_service.get()

        instances = list(manifestations_from_deployment(
            deployment, volume[u"dataset_id"]))

        if not any(m for (m, _) in instances if not m.dataset.deleted):
            raise DATASET_NOT_FOUND
        if not any(n for (_, n) in instances if n.uuid == node_uuid):
            raise DATASET_ON_DIFFERENT_NODE
        if any(app for app in deployment.applications() if
                app.volume and
                app.volume.manifestation.dataset_id == volume[u"dataset_id"]):
            raise DATASET_IN_USE

        return AttachedVolume(
            manifestation=[m for (m, node) in instances
                           if node.uuid == node_uuid and m.primary][0],
            mountpoint=FilePath(volume[u"mountpoint"].encode("utf-8")))

    @app.route("/configuration/containers", methods=['POST'])
    @user_documentation(
        u"""
        The container will be automatically started once it is created on
        the cluster.
        """,
        header=u"Add a new container to the configuration",
        examples=[
            u"create container",
            u"create container with duplicate name",
            u"create container with ports",
            u"create container with environment",
            u"create container with attached volume",
            u"create container with cpu shares",
            u"create container with memory limit",
            u"create container with links",
            u"create container with command line",
            # No example of creating a container with a different restart
            # policy because only the "never" policy is supported.  See
            # FLOC-2449.
        ],
        section=u"container",
    )
    @structured(
        inputSchema={
            '$ref': '/v1/endpoints.json#/definitions/configuration_container'},
        outputSchema={
            '$ref': '/v1/endpoints.json#/definitions/configuration_container'},
        schema_store=SCHEMAS
    )
    def create_container_configuration(
        self, node_uuid, name, image, ports=(), environment=None,
        restart_policy=None, cpu_shares=None, memory_limit=None,
        links=(), volumes=(), command_line=None,
    ):
        """
        Create a new dataset in the cluster configuration.

        :param unicode node_uuid: The UUID of the node on which the container
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

        :param dict restart_policy: A restart policy for the container, this
            is a ``dict`` with at a minimum a "name" key, whose value must be
            one of "always", "never" or "on-failure". If the "name" is given
            as "on-failure", there may also be another optional key
            "maximum_retry_count", containing a positive ``int`` specifying
            the maximum number of times we should attempt to restart a failed
            container.

        :param volumes: A iterable of ``dict`` with ``"dataset_id"`` and
            ``"mountpoint"`` keys.

        :param int cpu_shares: A positive integer specifying the relative
            weighting of CPU cycles for this container (see Docker's run
            reference for further information).

        :param int memory_limit: A positive integer specifying the maximum
            amount of memory in bytes available to this container.

        :param list links: A ``list`` of ``dict`` objects, mapping container
            links via "alias", "local_port" and "remote_port" values.

        :param command_line: If not ``None``, the command line to use when
            running the Docker image's entry point.

        :return: An ``EndpointResponse`` describing the container which has
            been added to the cluster configuration.
        """
        deployment = self.persistence_service.get()

        node_uuid = UUID(hex=node_uuid)

        # Check if container by this name already exists, if it does
        # return error.
        for node in deployment.nodes:
            for application in node.applications:
                if application.name == name:
                    raise CONTAINER_NAME_COLLISION

        # Find the volume, if any; currently we only support one volume
        # https://clusterhq.atlassian.net/browse/FLOC-49
        attached_volume = None
        if volumes:
            attached_volume = self._get_attached_volume(node_uuid, volumes[0])

        # Find the node.
        node = deployment.get_node(node_uuid)

        # Check if we have any ports in the request. If we do, check existing
        # external ports exposed to ensure there is no conflict. If there is a
        # conflict, return an error.
        for port in ports:
            for current_node in deployment.nodes:
                for application in current_node.applications:
                    for application_port in application.ports:
                        if application_port.external_port == port['external']:
                            raise CONTAINER_PORT_COLLISION

        # If links are present, check that there are no conflicts in local
        # ports or alias names.
        link_aliases = set()
        link_local_ports = set()
        application_links = set()
        for link in links:
            if link['alias'] in link_aliases:
                raise LINK_ALIAS_COLLISION
            if link['local_port'] in link_local_ports:
                raise LINK_PORT_COLLISION
            link_aliases.add(link['alias'])
            link_local_ports.add(link['local_port'])
            application_links.add(
                Link(
                    alias=link['alias'], local_port=link['local_port'],
                    remote_port=link['remote_port']
                )
            )

        # If we have ports specified, add these to the Application instance.
        application_ports = []
        for port in ports:
            application_ports.append(Port(
                internal_port=port['internal'],
                external_port=port['external']
            ))

        if environment is not None:
            environment = frozenset(environment.items())

        if restart_policy is None:
            restart_policy = dict(name=u"never")

        policy_name = restart_policy.pop("name")
        policy_factory = FLOCKER_RESTART_POLICY_NAME_TO_POLICY[policy_name]
        policy = policy_factory(**restart_policy)

        # Create Application object, add to Deployment, save.
        application = Application(
            name=name,
            image=DockerImage.from_string(image),
            ports=frozenset(application_ports),
            environment=environment,
            volume=attached_volume,
            restart_policy=policy,
            cpu_shares=cpu_shares,
            memory_limit=memory_limit,
            links=application_links,
            command_line=command_line,
        )

        new_node_config = node.transform(
            ["applications"],
            lambda s: s.add(application)
        )

        new_deployment = deployment.update_node(new_node_config)
        saving = self.persistence_service.save(new_deployment)

        # Return passed in dictionary with CREATED response code.
        def saved(_):
            result = container_configuration_response(application, node_uuid)
            return EndpointResponse(CREATED, result)
        saving.addCallback(saved)
        return saving

    @app.route("/configuration/containers/<name>", methods=['POST'])
    @user_documentation(
        u"""
        This will lead to the container being relocated to the specified host
        and restarted. This will also update the primary host of any attached
        datasets.
        """,
        header=u"Update a named container's configuration",
        examples=[u"move container"],
        section=u"container",
    )
    @structured(
        inputSchema={
            '$ref':
            '/v1/endpoints.json#/definitions/configuration_container_update',
        },
        outputSchema={
            '$ref':
            '/v1/endpoints.json#/definitions/configuration_container',
        },
        schema_store=SCHEMAS,
    )
    def update_containers_configuration(self, name, node_uuid):
        """
        Update the specified container's configuration.

        :param unicode name: A unique identifier for the container within
            the Flocker cluster.

        :param unicode node_uuid: The address of the node on which the
            container will run.

        :return: An ``EndpointResponse`` describing the container which has
            been updated.
        """
        deployment = self.persistence_service.get()
        node_uuid = UUID(hex=node_uuid)
        target_node = deployment.get_node(node_uuid)
        for node in deployment.nodes:
            for application in node.applications:
                if application.name == name:
                    deployment = deployment.move_application(
                        application, target_node
                    )
                    saving = self.persistence_service.save(deployment)

                    def saved(_, application=application):
                        result = container_configuration_response(
                            application, node_uuid
                        )
                        return EndpointResponse(OK, result)

                    saving.addCallback(saved)
                    return saving

        # Didn't find the application:
        raise CONTAINER_NOT_FOUND

    @app.route("/configuration/containers/<name>", methods=['DELETE'])
    @user_documentation(
        u"""
        This will lead to the container being stopped and not being
        restarted again. Any datasets that were attached as volumes will
        continue to exist on the cluster.
        """,
        header=u"Remove a container from the configuration",
        examples=[
            u"remove a container",
            u"remove a container with unknown name",
        ],
        section=u"container",
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
                        ["applications"],
                        lambda s, application=application: s.remove(
                            application))
                    d = self.persistence_service.save(
                        deployment.update_node(updated_node))
                    d.addCallback(lambda _: None)
                    return d

        # Didn't find the application:
        raise CONTAINER_NOT_FOUND

    @app.route("/state/nodes", methods=['GET'])
    @user_documentation(
        u"""
        Some nodes may not be listed if their agents are disconnected from
        the cluster. IP addresses may be private IP addresses that are not
        publicly routable.
        """,
        header=u"List known nodes in the cluster",
        examples=[
            u"list known nodes",
        ],
        section=u"common",
    )
    @structured(
        inputSchema={},
        outputSchema={"$ref":
                      '/v1/endpoints.json#/definitions/nodes_array'},
        schema_store=SCHEMAS
    )
    def list_current_nodes(self):
        return [{u"host": node.hostname, u"uuid": unicode(node.uuid)}
                for node in
                self.cluster_state_service.as_deployment().nodes]

    @app.route("/state/nodes/by_era/<era>", methods=['GET'])
    @user_documentation(
        u"""
        If you are talking to the API from a process on a node then this
        is the recommended way of figuring out the node UUID. Since eras
        are reset on reboot, looking up by era means you will never get
        stale pre-reboot state.

        You can discover a node's era by running the ``flocker-node-era``
        command-line tool on the relevant node. Make sure you don't cache
        this information across reboots!

        If the era is unknown you will get a 404 HTTP response. In this
        case retry until the node UUID is returned.
        """,
        header=u"Lookup a node by its era",
        examples=[
            u"get node by era",
        ],
        section=u"common",
    )
    @structured(
        inputSchema={},
        outputSchema={"$ref":
                      '/v1/endpoints.json#/definitions/node'},
        schema_store=SCHEMAS
    )
    def get_node_by_era(self, era):
        era = UUID(era)
        cluster_state = self.cluster_state_service.as_deployment()
        era_to_node_uuid = dict(
            (era, node_uuid) for (node_uuid, era) in
            cluster_state.node_uuid_to_era.items())
        try:
            node_uuid = era_to_node_uuid[era]
        except KeyError:
            raise NODE_BY_ERA_NOT_FOUND
        return {u"uuid": unicode(node_uuid)}

    @app.route("/configuration/_compose", methods=['POST'])
    @private_api
    @structured(
        inputSchema={
            '$ref':
            '/v1/endpoints.json#/definitions/configuration_compose'
        },
        outputSchema={},
        schema_store=SCHEMAS
    )
    def replace_configuration(self, applications, deployment):
        """
        Replace the existing configuration with one given by flocker-deploy
        command line tool.

        :param applications: Configuration in Flocker-native or
            Fig/Compose format.

        :param deployment: Configuration of which applications run on
            which nodes.
        """
        try:
            configuration = FigConfiguration(applications)
            if not configuration.is_valid_format():
                configuration = FlockerConfiguration(applications)
            return self.persistence_service.save(model_from_configuration(
                deployment_state=self.cluster_state_service.as_deployment(),
                applications=configuration.applications(),
                deployment_configuration=deployment))
        except ConfigurationError as e:
            raise make_bad_request(code=BAD_REQUEST, description=unicode(e))

    @app.route("/configuration/leases", methods=['GET'])
    @user_documentation(
        u"""
        List the currently existing leases on datasets, including which
        node the lease is for and when if ever the lease will expire.
        """,
        header=u"List all leases on datasets",
        examples=[
            u"list leases",
        ],
        section=u"dataset",
    )
    @structured(
        inputSchema={},
        outputSchema={
            '$ref':
            '/v1/endpoints.json#/definitions/list_leases'
        },
        schema_store=SCHEMAS
    )
    def list_leases(self):
        """
        List the current leases in the configuration.
        """
        now = datetime.fromtimestamp(self.clock.seconds(), UTC)
        result = []
        for lease in self.persistence_service.get().leases.values():
            result.append(lease_response(lease, now))
        return result

    @app.route("/configuration/leases/<dataset_id>", methods=['DELETE'])
    @user_documentation(
        u"""
        This will release a lease on a dataset, allowing the dataset to be
        moved elsewhere, deleted and otherwise modified. Releasing the
        lease does not modify the dataset in any way, it simply allows
        other operations to do so.
        """,
        header=u"Release a lease on a dataset",
        examples=[
            u"release a lease",
        ],
        section=u"dataset",
    )
    @structured(
        inputSchema={},
        outputSchema={'$ref': '/v1/endpoints.json#/definitions/lease'},
        schema_store=SCHEMAS
    )
    def delete_lease(self, dataset_id):
        """
        Remove a lease from the cluster configuration.

        :param unicode dataset_id: The dataset whose lease is being
            removed.

        :return: A ``Deferred`` firing with an ``EndpointResponse`` or
            serializable JSON.
        """
        now = datetime.fromtimestamp(self.clock.seconds(), UTC)
        leases = self.persistence_service.get().leases
        dataset_id = UUID(dataset_id)

        lease = leases.get(dataset_id, None)
        if lease is not None:
            d = update_leases(
                # We could choose to design a REST endpoint that requires
                # taking the node UUID, but it's not clear what particular
                # safety that adds... so just accept all releases.
                lambda leases: leases.release(dataset_id, lease.node_id),
                self.persistence_service)
            d.addCallback(lambda _: lease_response(lease, now))
            return d
        else:
            # Didn't find the lease:
            raise LEASE_NOT_FOUND

    @app.route("/configuration/leases", methods=['POST'])
    @user_documentation(
        u"""
        Acquire a lease on a particular dataset on a particular
        node. Until the lease is released or expires the dataset will not
        be deleted or moved to other nodes.
        """,
        header=u"Acquire a lease on a dataset",
        examples=[
            u"acquire a lease without expiration",
            u"acquire a lease with expiration",
            u"acquire a lease that is already held",
            u"renew a lease",
        ],
        section=u"dataset",
    )
    @structured(
        inputSchema={'$ref': '/v1/endpoints.json#/definitions/lease'},
        outputSchema={'$ref': '/v1/endpoints.json#/definitions/lease'},
        schema_store=SCHEMAS
    )
    def acquire_lease(self, dataset_id, node_uuid, expires):
        """
        Acquire a lease on a dataset.

        :param unicode dataset_id: The dataset whose lease is being
            acquired.
        :param unicode node_uuid: The node on which the lease is being aquired.
        :param expires: ``None`` if no expiration, otherwise number of
            seconds to expiration.

        :return: A ``Deferred`` firing with an ``EndpointResponse`` or
            serializable JSON.
        """
        now = datetime.fromtimestamp(self.clock.seconds(), UTC)
        dataset_id = UUID(dataset_id)
        node_uuid = UUID(node_uuid)

        # Check if already exists or not:
        if self.persistence_service.get().leases.get(dataset_id) is None:
            response_code = CREATED
        else:
            response_code = OK

        def acquire(leases):
            try:
                return leases.acquire(now, dataset_id, node_uuid, expires)
            except LeaseError:
                raise LEASE_HELD

        d = update_leases(acquire, self.persistence_service)
        d.addCallback(
            lambda leases: EndpointResponse(
                response_code, lease_response(leases[dataset_id], now)))
        return d


def _find_manifestation_and_node(deployment, dataset_id):
    """
    Given the ID of a dataset, find its primary manifestation and the node
    it's on.

    :param unicode dataset_id: The unique identifier of the dataset.  This
        is a string giving a UUID (per RFC 4122).

    :return: Tuple containing the primary ``Manifestation`` and the
        ``Node`` it is on.
    """
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


def _update_dataset_primary(deployment, dataset_id, primary):
    """
    Update the ``deployment`` so that the ``Dataset`` with the supplied
    ``dataset_id`` is on the ``Node`` with the supplied ``primary`` address.

    :param Deployment deployment: The deployment containing the dataset to be
        updated.
    :param unicode dataset_id: The ID of the dataset to be updated.
    :param UUID primary: The UUID of the new primary node of the
        supplied ``dataset_id``.
    :returns: An updated ``Deployment``.
    """
    primary_manifestation, old_primary_node = _find_manifestation_and_node(
        deployment, dataset_id
    )
    # Now construct a new_deployment where the primary manifestation of the
    # dataset is on the requested primary node.
    old_primary_node = old_primary_node.transform(
        ("manifestations", primary_manifestation.dataset_id), discard
    )
    deployment = deployment.update_node(old_primary_node)

    new_primary_node = deployment.get_node(primary)
    new_primary_node = new_primary_node.transform(
        ("manifestations", dataset_id), primary_manifestation
    )

    deployment = deployment.update_node(new_primary_node)
    return deployment


def _update_dataset_maximum_size(deployment, dataset_id, maximum_size):
    """
    Update the ``deployment`` so that the ``Dataset`` with the supplied
    ``dataset_id`` has the supplied ``maximum_size``.

    :param Deployment deployment: The deployment containing the dataset to be
        updated.
    :param unicode dataset_id: The ID of the dataset to be updated.
    :param maximum_size: The new size of the dataset or ``None`` to remove the
        size limit.
    :returns: An updated ``Deployment``.
    """
    _, node = _find_manifestation_and_node(deployment, dataset_id)
    deployment = deployment.set(nodes=deployment.nodes.discard(node))
    node = node.transform(
        ['manifestations', dataset_id, 'dataset', 'maximum_size'],
        maximum_size
    )
    return deployment.set(nodes=deployment.nodes.add(node))


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
        if node.manifestations is None:
            continue
        for manifestation in node.manifestations.values():
            if manifestation.primary:
                # There may be multiple datasets marked as primary until we
                # implement consistency checking when state is reported by each
                # node.
                # See https://clusterhq.atlassian.net/browse/FLOC-1303
                yield api_dataset_from_dataset_and_node(
                    manifestation.dataset, node.uuid
                )


@lru_cache(1)
def _containers_from_deployment(deployment):
    """
    Extract the containers from the supplied deployment instance.

    N.B.: Callers of this function should not mutate the returned value as this
    function uses an lru_cache.

    :param Deployment deployment: A ``Deployment`` describing the state
        of the cluster.

    :return: List of all containers.
    """
    results = []
    for node in deployment.nodes:
        for application in node.applications:
            results.append(
                container_configuration_response(application, node.uuid)
            )
    return results


def container_configuration_response(application, node):
    """
    Return a container dict  which confirms to
    ``/v1/endpoints.json#/definitions/configuration_container``

    :param Application application: An ``Application`` instance.
    :param UUID node: The host on which this application is running.
    :return: A ``dict`` containing the container configuration.
    """
    result = {
        "node_uuid": unicode(node), "name": application.name,
    }
    result.update(ApplicationMarshaller(application).convert())
    # Configuration format isn't quite the same as JSON format:
    if u"volume" in result:
        # Config format includes maximum_size, which we don't want:
        volume = result.pop(u"volume")
        result[u"volumes"] = [{u"dataset_id": volume[u"dataset_id"],
                               u"mountpoint": volume[u"mountpoint"]}]
    if application.cpu_shares is not None:
        result["cpu_shares"] = application.cpu_shares
    if application.memory_limit is not None:
        result["memory_limit"] = application.memory_limit
    if application.command_line is not None:
        result["command_line"] = list(application.command_line)
    return result


def api_dataset_from_dataset_and_node(dataset, node_uuid):
    """
    Return a dataset dict which conforms to
    ``/v1/endpoints.json#/definitions/configuration_datasets_array``

    :param Dataset dataset: A dataset present in the cluster.
    :param UUID node_uuid: UUID of the primary node for the
        `dataset`.
    :return: A ``dict`` containing the dataset information and the
        hostname of the primary node, conforming to
        ``/v1/endpoints.json#/definitions/configuration_datasets_array``.
    """
    result = dict(
        dataset_id=dataset.dataset_id,
        deleted=dataset.deleted,
        primary=unicode(node_uuid),
        metadata=thaw(dataset.metadata)
    )
    if dataset.maximum_size is not None:
        result[u'maximum_size'] = dataset.maximum_size
    return result


def create_api_service(persistence_service, cluster_state_service, endpoint,
                       context_factory, clock=reactor):
    """
    Create a Twisted Service that serves the API on the given endpoint.

    :param ConfigurationPersistenceService persistence_service: Service
        for retrieving and setting desired configuration.

    :param ClusterStateService cluster_state_service: Service that
        knows about the current state of the cluster.

    :param endpoint: Twisted endpoint to listen on.

    :param context_factory: TLS context factory.

    :param IReactorTime clock: The clock to use for time. By default
        global reactor.

    :return: Service that will listen on the endpoint using HTTP API server.
    """
    api_root = Resource()
    user = ConfigurationAPIUserV1(persistence_service, cluster_state_service,
                                  clock)
    api_root.putChild('v1', user.app.resource())
    api_root._v1_user = user  # For unit testing purposes, alas

    return StreamServerEndpointService(
        endpoint,
        TLSMemoryBIOFactory(
            context_factory,
            False,
            Site(api_root)
        )
    )


def lease_response(lease, now):
    """
    Convert a ``Lease`` to the corresponding objects for JSON
    serialization.

    :param Lease lease: The lease to serialize.
    :param datetime now: The current time.
    :return: ``dict`` form that matches the lease schema.
    """
    if lease.expiration is None:
        expires = None
    else:
        expires = (lease.expiration - now).total_seconds()
    return {u"dataset_id": unicode(lease.dataset_id),
            u"node_uuid": unicode(lease.node_id),
            u"expires": expires}
