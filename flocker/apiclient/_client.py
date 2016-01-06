# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Client for the Flocker REST API.
"""

from uuid import UUID, uuid4
from json import dumps
from datetime import datetime
from os import environ

from ipaddr import IPv4Address, IPv6Address, IPAddress

from pytz import UTC

from zope.interface import Interface, implementer

from pyrsistent import PClass, field, pmap_field, pmap

from eliot import ActionType, Field
from eliot.twisted import DeferredContext

from twisted.internet.defer import succeed, fail
from twisted.python.filepath import FilePath
from twisted.web.http import (
    CREATED, OK, CONFLICT, NOT_FOUND, PRECONDITION_FAILED,
)
from twisted.internet.utils import getProcessOutput
from twisted.internet.task import deferLater

from treq import json_content, content

from ..ca import treq_with_authentication
from ..control import Leases as LeasesModel, LeaseError, DockerImage
from ..common import retry_failure

from .. import __version__

_LOG_HTTP_REQUEST = ActionType(
    "flocker:apiclient:http_request",
    [Field.forTypes("url", [bytes, unicode], "Request URL."),
     Field.forTypes("method", [bytes, unicode], "Request method."),
     Field("request_body", lambda o: o, "Request JSON body.")],
    [Field.forTypes("response_code", [int], "Response code."),
     Field("response_body", lambda o: o, "JSON response body.")],
    "A HTTP request.")

_LOG_CONDITIONAL_CREATE = ActionType(
    u"flocker:apiclient:conditional_create", [], [],
    u"Conditionally create a dataset.")


NoneType = type(None)


class ServerResponseMissingElementError(Exception):
    """
    Output the invalid server response if a response does not contain an
    expected JSON object attribute.
    """
    def __init__(self, key, response):
        message = u'{!r} not found in {!r}'.format(key, response)
        Exception.__init__(self, message)


class Dataset(PClass):
    """
    A dataset in the configuration.

    :attr UUID primary: The node where the dataset should manifest.
    :attr int|None maximum_size: Size of the dataset in bytes or ``None``
        if no particular size was requested.
    :attr UUID dataset_id: The UUID of the dataset.
    :attr metadata: A mapping between unicode keys and values.
    """
    dataset_id = field(type=UUID, mandatory=True)
    primary = field(type=UUID, mandatory=True)
    maximum_size = field(type=(int, NoneType), mandatory=True)
    metadata = pmap_field(unicode, unicode)


class DatasetState(PClass):
    """
    The state of a dataset in the cluster.

    :attr primary: The ``UUID`` of the node where the dataset is manifest,
        or ``None`` if it has no primary manifestation.
    :attr int|None maximum_size: Maximum size of the dataset in bytes, or
        ``None`` if the maximum size is not set.
    :attr UUID dataset_id: The UUID of the dataset.
    :attr FilePath|None path: Filesytem path where the dataset is mounted,
        or ``None`` if not mounted.
    """
    dataset_id = field(type=UUID, mandatory=True)
    primary = field(type=(UUID, NoneType), mandatory=True)
    maximum_size = field(type=(int, NoneType), mandatory=True)
    path = field(type=(FilePath, NoneType), mandatory=True)


class Lease(PClass):
    """
    A lease on a dataset.

    :attr UUID dataset_id: The dataset for which the lease applies.
    :attr UUID node_uuid: The node for which the lease applies.
    :attr None|float|int expires: Time in seconds until lease expires, or
        ``None`` if it will not expire.
    """
    dataset_id = field(type=UUID, mandatory=True)
    node_uuid = field(type=UUID, mandatory=True)
    expires = field(type=(float, int, NoneType), mandatory=True)


class MountedDataset(PClass):
    """
    A mounted dataset.

    :attr UUID dataset_id: The UUID of the dataset.
    :attr unicode mountpoint: The filesystem location of the dataset.
    """
    dataset_id = field(type=UUID, mandatory=True)
    mountpoint = field(type=unicode, mandatory=True)


def _parse_volumes(data_list):
    """
    Parse a list of volume configuration.

    :param Optional[Sequence[Mapping[unicode, unicode]]] data_list: Sequence
        of data describing volume objects.
    :return Optional[Sequence[MountedDataset]]: Sequence of mounted datasets,
        or None if no volumes.
    """
    if data_list:
        return [
            MountedDataset(
                dataset_id=UUID(data[u'dataset_id']),
                mountpoint=data[u'mountpoint'],
            ) for data in data_list
        ]
    else:
        return None


class Container(PClass):
    """
    A container in the configuration.

    :attr UUID node_uuid: The UUID of a node in the cluster where the
        container will run.
    :attr unicode name: The unique name of the container.
    :attr DockerImage image: The Docker image the container will run.
    :attr Optional[Sequence[MountedDataset]] volumes: Flocker volumes
        mounted in container.
    """
    node_uuid = field(type=UUID, mandatory=True)
    name = field(type=unicode, mandatory=True)
    image = field(type=DockerImage, mandatory=True)
    volumes = field(initial=None)


class ContainerState(PClass):
    """
    The state of a container in the cluster.

    :attr UUID node_uuid: The UUID of a node in the cluster where the
        container will run.
    :attr unicode name: The unique name of the container.
    :attr DockerImage image: The name of the Docker image.
    :attr bool running: Whether the container is running.
    :attr Optional[Sequence[MountedDataset]] volumes: Flocker volumes
        mounted in container.
    """
    node_uuid = field(type=UUID, mandatory=True)
    name = field(type=unicode, mandatory=True)
    image = field(type=DockerImage, mandatory=True)
    running = field(type=bool, mandatory=True)
    volumes = field(initial=None, mandatory=True)


class Node(PClass):
    """
    A node on which a Flocker agent is running.

    :attr UUID uuid: The UUID of the node.
    :attr IPAddress public_address: The public IP address of the node.
    """
    uuid = field(type=UUID, mandatory=True)
    public_address = field(
        type=(IPv4Address, IPv6Address),
        mandatory=True,
    )


class DatasetAlreadyExists(Exception):
    """
    The suggested dataset ID already exists.
    """


class LeaseAlreadyHeld(Exception):
    """
    A lease exists for the specified dataset ID on a different node.
    """


class ContainerAlreadyExists(Exception):
    """
    The specified container name is in use by another container.
    """


class ConfigurationChanged(Exception):
    """
    An action that required a specific version of the configuration failed
    because the configuration has changed on the server.
    """


class DatasetsConfiguration(PClass):
    """
    Currently configured datasets.

    :ivar tag: The current version of the configuration, suitable for
        passing as conditional to operations like creation.
    :ivar datasets: The current ``Dataset`` on the server; maps ``UUID``
        to ``Dataset``.
    """
    tag = field(mandatory=True)
    datasets = pmap_field(UUID, Dataset)

    def __iter__(self):
        """
        :return: Iterator over ``Dataset`` instances.
        """
        return self.datasets.itervalues()


class IFlockerAPIV1Client(Interface):
    """
    The Flocker REST API v1 client.

    Operations that take a ``configuration_tag`` parameter will fail with
    a ``ConfigurationChanged`` if the configuration has changed since the
    matching ``list_datasets_configuration`` call.
    """
    def create_dataset(primary, maximum_size=None, dataset_id=None,
                       metadata=pmap(), configuration_tag=None):
        """
        Create a new dataset in the configuration.

        :param UUID primary: The node where the dataset should manifest.
        :param maximum_size: Size of new dataset in bytes (as ``int``) or
            ``None`` if no particular size is required (not recommended).
        :param dataset_id: If given, the UUID to use for the dataset.
        :param metadata: A mapping between unicode keys and values, to be
            stored as dataset metadata.
        :param configuration_tag: If not ``None``, should be
            ``DatasetsConfiguration.tag``.

        :return: ``Deferred`` that fires after the configuration has been
            updated with resulting ``Dataset``, or errbacking with
            ``DatasetAlreadyExists``.
        """

    def move_dataset(primary, dataset_id, configuration_tag=None):
        """
        Move the dataset to a new location.

        :param UUID primary: The node where the dataset should manifest.
        :param dataset_id: Which dataset to move.
        :param configuration_tag: If not ``None``, should be
            ``DatasetsConfiguration.tag``.

        :return: ``Deferred`` that fires after the configuration has been
            updated with the resulting ``Dataset``.
        """

    def delete_dataset(dataset_id, configuration_tag=None):
        """
        Delete a dataset.

        :param dataset_id: The UUID of the dataset to be deleted.
        :param configuration_tag: If not ``None``, should be
            ``DatasetsConfiguration.tag``.

        :return: ``Deferred`` that fires with the ``Dataset`` that has just
        been deleted, after the configuration has been updated.
        """

    def list_datasets_configuration():
        """
        Return the configured datasets, excluding any datasets that
        have been deleted.

        :return: ``Deferred`` firing with a ``DatasetsConfiguration``.
        """

    def list_datasets_state():
        """
        Return the actual datasets in the cluster.

        :return: ``Deferred`` firing with iterable of ``DatasetState``.
        """

    def acquire_lease(dataset_id, node_uuid, expires):
        """
        Acquire a lease on a dataset on a given node.

        If the lease already exists for the given dataset and node then
        this will renew the lease.

        :param UUID dataset_id: The dataset for which the lease applies.
        :param UUID node_uuid: The node for which the lease applies.
        :param None|float expires: Time in seconds until lease expires, or
            ``None`` if it will not expire.

        :return: ``Deferred`` firing with a ``Lease`` or failing with
            ``LeaseAlreadyHeld`` if the lease for this dataset is held for a
            different node.
        """

    def release_lease(dataset_id):
        """
        Release a lease.

        :param UUID dataset_id: The dataset for which the lease applies.

        :return: ``Deferred`` firing with the released ``Lease`` on success.
        """

    def list_leases():
        """
        Return current leases.

        :return: ``Deferred`` firing with a list of ``Lease`` instance.
        """

    def version():
        """
        Return current version.

        :return: ``Deferred`` firing with a ``dict`` containing the key
            ``flocker`` and the version reported by the Flocker Control
            service.
        """

    def list_nodes():
        """
        Get information about active cluster nodes.

        :return: ``Deferred`` firing with a ``list`` of ``Node``.
        """

    def create_container(node_uuid, name, image, volumes=None):
        """
        :param UUID node_uuid: The ``UUID`` of the node where the container
            will be started.
        :param unicode name: The name to assign to the container.
        :param DockerImage image: The Docker image which the container will
            run.
        :param Optional[Sequence[MountedDataset]] volumes: Volumes to mount on
            container.

        :return: ``Deferred`` firing with the configured ``Container`` or
            ``ContainerAlreadyExists`` if the supplied container name already
            exists.
        """

    def list_containers_configuration():
        """
        :return: ``Deferred`` firing with ``iterable`` of ``Container``.
        """

    def list_containers_state():
        """
        Return the actual containers in the cluster.

        :return: ``Deferred`` firing with ``iterable`` of ``ContainerState``.
        """

    def delete_container(name):
        """
        :param unicode name: The name of the container to be deleted.

        :return: ``Deferred`` firing with the deleted ``Container``.
        """

    def this_node_uuid():
        """
        Return this node's UUID by looking it up by era.

        This is the recommended way of discovering the node UUID.
        """


@implementer(IFlockerAPIV1Client)
class FakeFlockerClient(object):
    """
    Fake in-memory implementation of ``IFlockerAPIV1Client``.
    """
    # Placeholder time, we don't model the progress of time at all:
    _NOW = datetime.fromtimestamp(0, UTC)

    def __init__(self, nodes=None, this_node_uuid=uuid4()):
        self._configured_datasets = pmap()
        self._configured_containers = pmap()
        self._leases = LeasesModel()
        if nodes is None:
            nodes = []
        self._nodes = nodes
        self._this_node_uuid = this_node_uuid
        self.synchronize_state()

    def _ensure_matching_tag(self, configuration_tag):
        """
        If the configuration tag doesn't match current config, raise
        ``ConfigurationChanged``.
        """
        if configuration_tag is not None:
            if configuration_tag != self._configured_datasets:
                raise ConfigurationChanged()

    def create_dataset(self, primary, maximum_size=None, dataset_id=None,
                       metadata=pmap(), configuration_tag=None):
        try:
            self._ensure_matching_tag(configuration_tag)
        except:
            return fail()

        # In real implementation the server will generate the new ID, but
        # we have to do it ourselves:
        if dataset_id is None:
            dataset_id = uuid4()
        if dataset_id in self._configured_datasets:
            return fail(DatasetAlreadyExists())
        result = Dataset(primary=primary, maximum_size=maximum_size,
                         dataset_id=dataset_id, metadata=metadata)
        self._configured_datasets = self._configured_datasets.set(
            dataset_id, result)
        return succeed(result)

    def delete_dataset(self, dataset_id, configuration_tag=None):
        try:
            self._ensure_matching_tag(configuration_tag)
        except:
            return fail()

        dataset = self._configured_datasets[dataset_id]
        self._configured_datasets = self._configured_datasets.remove(
            dataset_id)
        return succeed(dataset)

    def move_dataset(self, primary, dataset_id, configuration_tag=None):
        try:
            self._ensure_matching_tag(configuration_tag)
        except:
            return fail()

        self._configured_datasets = self._configured_datasets.transform(
            [dataset_id, "primary"], primary)
        return succeed(self._configured_datasets[dataset_id])

    def list_datasets_configuration(self):
        return succeed(DatasetsConfiguration(
            # Since the tag is opaque object, using the actual configuration
            # is a fine way to have a matching tag.
            tag=self._configured_datasets,
            datasets=self._configured_datasets))

    def list_datasets_state(self):
        return succeed(self._state_datasets)

    def synchronize_state(self):
        """
        Copy configuration into state.
        """
        self._state_datasets = [
            DatasetState(
                dataset_id=dataset.dataset_id,
                primary=dataset.primary,
                maximum_size=dataset.maximum_size,
                path=FilePath(b"/flocker").child(bytes(dataset.dataset_id))
            ) for dataset in self._configured_datasets.values()
        ]
        self._state_containers = [
            ContainerState(
                node_uuid=container.node_uuid,
                name=container.name,
                image=container.image,
                running=True,
                volumes=container.volumes,
            ) for container in self._configured_containers.values()
        ]

    def acquire_lease(self, dataset_id, node_uuid, expires):
        try:
            self._leases = self._leases.acquire(
                self._NOW, dataset_id, node_uuid, expires)
        except LeaseError:
            return fail(LeaseAlreadyHeld())
        return succeed(
            Lease(dataset_id=dataset_id, node_uuid=node_uuid, expires=expires))

    def release_lease(self, dataset_id):
        # We don't handle the case where lease doesn't exist yet, since
        # it's not clear that's necessary yet. If it is we'll need to
        # expand this logic.
        lease = self._leases[dataset_id]
        self._leases = self._leases.release(dataset_id, lease.node_id)
        return succeed(
            Lease(dataset_id=dataset_id, node_uuid=lease.node_id,
                  expires=((lease.expiration - self._NOW).total_seconds()
                           if lease.expiration is not None else None)))

    def list_leases(self):
        return succeed([
            Lease(dataset_id=l.dataset_id, node_uuid=l.node_id,
                  expires=((l.expiration - self._NOW).total_seconds()
                           if l.expiration is not None else None))
            for l in self._leases.values()])

    def version(self):
        return succeed(
            {u"flocker": __version__}
        )

    def list_nodes(self):
        return succeed(self._nodes)

    def create_container(self, node_uuid, name, image, volumes=None):
        if name in self._configured_containers:
            return fail(ContainerAlreadyExists())
        result = Container(
            node_uuid=node_uuid,
            name=name,
            image=image,
            volumes=volumes,
        )
        self._configured_containers = self._configured_containers.set(
            name, result
        )
        return succeed(result)

    def list_containers_configuration(self):
        return succeed(self._configured_containers.values())

    def list_containers_state(self):
        return succeed(self._state_containers)

    def delete_container(self, name):
        self._configured_containers = self._configured_containers.remove(name)
        return succeed(None)

    def this_node_uuid(self):
        return succeed(self._this_node_uuid)


class ResponseError(Exception):
    """
    An unexpected response from the REST API.
    """
    def __init__(self, code, body):
        Exception.__init__(self, "Unexpected response code {}:\n{}\n".format(
            code, body))
        self.code = code


class NotFound(Exception):
    """
    Result was not found.
    """


@implementer(IFlockerAPIV1Client)
class FlockerClient(object):
    """
    A client for the Flocker V1 REST API.
    """
    def __init__(self, reactor, host, port,
                 ca_cluster_path, cert_path, key_path):
        """
        :param reactor: Reactor to use for connections.
        :param bytes host: Host to connect to.
        :param int port: Port to connect to:
        :param FilePath ca_cluster_path: Path to cluster's CA certificate.
        :param FilePath cert_path: Path to user certificate.
        :param FilePath key_path: Path to user private key.
        """
        self._reactor = reactor
        self._treq = treq_with_authentication(reactor, ca_cluster_path,
                                              cert_path, key_path)
        self._base_url = b"https://%s:%d/v1" % (host, port)

    def _request_with_headers(
            self, method, path, body, success_codes, error_codes=None,
            configuration_tag=None):
        """
        Send a HTTP request to the Flocker API, return decoded JSON body and
        headers.

        :param bytes method: HTTP method, e.g. PUT.
        :param bytes path: Path to add to base URL.
        :param body: If not ``None``, JSON encode this and send as the
            body of the request.
        :param set success_codes: Expected success response codes.
        :param error_codes: Mapping from HTTP response code to exception to be
            raised if it is present, or ``None`` to set no errors.
        :param configuration_tag: If not ``None``, include value as
            ``X-If-Configuration-Matches`` header.

        :return: ``Deferred`` firing a tuple of (decoded JSON,
            response headers).
        """
        url = self._base_url + path
        action = _LOG_HTTP_REQUEST(url=url, method=method, request_body=body)

        if error_codes is None:
            error_codes = {}

        def error(body, code):
            if code in error_codes:
                raise error_codes[code](body)
            raise ResponseError(code, body)

        def got_response(response):
            if response.code in success_codes:
                action.addSuccessFields(response_code=response.code)
                d = json_content(response)
                d.addCallback(lambda decoded_body:
                              (decoded_body, response.headers))
                return d
            else:
                d = content(response)
                d.addCallback(error, response.code)
                return d

        # Serialize the current task ID so we can trace logging across
        # processes:
        headers = {b"X-Eliot-Task-Id": action.serialize_task_id()}
        data = None
        if body is not None:
            headers["content-type"] = b"application/json"
            data = dumps(body)
        if configuration_tag is not None:
            headers["X-If-Configuration-Matches"] = [
                configuration_tag.encode("utf-8")]

        with action.context():
            request = DeferredContext(self._treq.request(
                method, url,
                data=data, headers=headers,
                # Keep tests from having dirty reactor problems:
                persistent=False
                ))
        request.addCallback(got_response)

        def got_body(result):
            action.addSuccessFields(response_body=result[0])
            return result
        request.addCallback(got_body)
        request.addActionFinish()
        return request.result

    def _request(self, *args, **kwargs):
        """
        Send a HTTP request to the Flocker API, return decoded JSON body.

        Takes the same arguments as ``_request_with_headers``.

        :return: ``Deferred`` firing with decoded JSON.
        """
        return self._request_with_headers(*args, **kwargs).addCallback(
            lambda t: t[0])

    def _parse_configuration_dataset(self, dataset_dict):
        """
        Convert a dictionary decoded from JSON with a dataset's configuration.

        :param dataset_dict: Dictionary describing a dataset.
        :return: ``Dataset`` instance.
        """
        return Dataset(primary=UUID(dataset_dict[u"primary"]),
                       maximum_size=dataset_dict.get(u"maximum_size", None),
                       dataset_id=UUID(dataset_dict[u"dataset_id"]),
                       metadata=dataset_dict[u"metadata"])

    def delete_dataset(self, dataset_id, configuration_tag=None):
        request = self._request(
            b"DELETE", b"/configuration/datasets/%s" % (dataset_id,),
            None, {OK}, {PRECONDITION_FAILED: ConfigurationChanged},
            configuration_tag=configuration_tag)
        request.addCallback(self._parse_configuration_dataset)
        return request

    def create_dataset(self, primary, maximum_size=None, dataset_id=None,
                       metadata=pmap(), configuration_tag=None):
        dataset = {u"primary": unicode(primary),
                   u"metadata": dict(metadata)}
        if dataset_id is not None:
            dataset[u"dataset_id"] = unicode(dataset_id)
        if maximum_size is not None:
            dataset[u"maximum_size"] = maximum_size
        request = self._request(b"POST", b"/configuration/datasets",
                                dataset, {CREATED},
                                {CONFLICT: DatasetAlreadyExists,
                                 PRECONDITION_FAILED: ConfigurationChanged},
                                configuration_tag=configuration_tag)
        request.addCallback(self._parse_configuration_dataset)
        return request

    def move_dataset(self, primary, dataset_id, configuration_tag=None):
        request = self._request(
            b"POST", b"/configuration/datasets/%s" % (dataset_id,),
            {u"primary": unicode(primary)}, {OK},
            {PRECONDITION_FAILED: ConfigurationChanged},
            configuration_tag=configuration_tag)
        request.addCallback(self._parse_configuration_dataset)
        return request

    def list_datasets_configuration(self):
        request = self._request_with_headers(
            b"GET", b"/configuration/datasets", None, {OK})
        request.addCallback(
            lambda (results, headers):
            DatasetsConfiguration(
                tag=headers.getRawHeaders('X-Configuration-Tag')[0],
                datasets={
                    UUID(d['dataset_id']): self._parse_configuration_dataset(d)
                    for d in results if not d['deleted']
                })
        )
        return request

    def list_datasets_state(self):
        request = self._request(b"GET", b"/state/datasets", None, {OK})

        def parse_dataset_state(dataset_dict):
            primary = dataset_dict.get(u"primary")
            if primary is not None:
                primary = UUID(primary)
            path = dataset_dict.get(u"path")
            if path is not None:
                path = FilePath(path)
            return DatasetState(primary=primary,
                                maximum_size=dataset_dict.get(
                                    u"maximum_size", None),
                                dataset_id=UUID(dataset_dict[u"dataset_id"]),
                                path=path)

        request.addCallback(
            lambda results: [parse_dataset_state(d) for d in results])
        return request

    def _parse_lease(self, dictionary):
        """
        Parse a result dictionary into a ``Lease``.

        :param dict dictionary: API JSON result.
        :return: Corresponding ``Lease``.
        """
        return Lease(dataset_id=UUID(dictionary[u"dataset_id"]),
                     node_uuid=UUID(dictionary[u"node_uuid"]),
                     expires=dictionary[u"expires"])

    def acquire_lease(self, dataset_id, node_uuid, expires=None):
        request = self._request(b"POST", b"/configuration/leases",
                                {u"dataset_id": unicode(dataset_id),
                                 u"node_uuid": unicode(node_uuid),
                                 u"expires": expires},
                                {OK, CREATED},
                                {CONFLICT: LeaseAlreadyHeld})
        request.addCallback(self._parse_lease)
        return request

    def release_lease(self, dataset_id):
        request = self._request(
            b"DELETE", b"/configuration/leases/" + bytes(dataset_id),
            None, {OK})
        request.addCallback(self._parse_lease)
        return request

    def list_leases(self):
        request = self._request(
            b"GET", b"/configuration/leases", None, {OK})
        request.addCallback(
            lambda results: [self._parse_lease(l) for l in results])
        return request

    def version(self):
        return self._request(
            b"GET", b"/version", None, {OK}
        )

    def _parse_configuration_container(self, container_dict):
        """
        Convert a dictionary decoded from JSON with a container's
        configuration.

        :param container_dict: Dictionary describing a container.
        :return: ``Container`` instance.
        """
        return Container(
            node_uuid=UUID(hex=container_dict[u"node_uuid"]),
            name=container_dict[u'name'],
            image=DockerImage.from_string(container_dict[u"image"]),
            volumes=_parse_volumes(container_dict.get(u'volumes')),
        )

    def create_container(self, node_uuid, name, image, volumes=None):
        container = dict(
            node_uuid=unicode(node_uuid), name=name, image=image.full_name,
        )
        if volumes:
            container[u'volumes'] = [
                {
                    u'dataset_id': unicode(volume.dataset_id),
                    u'mountpoint': volume.mountpoint
                } for volume in volumes
            ]
        d = self._request(
            b"POST",
            b"/configuration/containers",
            container,
            {CREATED},
            {CONFLICT: ContainerAlreadyExists},
        )
        d.addCallback(self._parse_configuration_container)
        return d

    def list_containers_configuration(self):
        d = self._request(b"GET", b"/configuration/containers", None, {OK})
        d.addCallback(
            lambda containers: list(
                self._parse_configuration_container(container_dict)
                for container_dict in containers
            )
        )
        return d

    def list_containers_state(self):
        d = self._request(b"GET", b"/state/containers", None, {OK})

        def parse(container):
            try:
                return ContainerState(
                    node_uuid=UUID(container[u'node_uuid']),
                    name=container[u'name'],
                    image=DockerImage.from_string(container[u'image']),
                    running=container[u'running'],
                    volumes=_parse_volumes(container.get(u'volumes'))
                )
            except KeyError as e:
                raise ServerResponseMissingElementError(e.args[0], container)
        d.addCallback(
            lambda containers: [parse(container) for container in containers])

        return d

    def list_nodes(self):
        request = self._request(
            b"GET", b"/state/nodes", None, {OK}
        )

        def to_nodes(result):
            """
            Turn the list of dicts into ``Node`` instances.
            """
            nodes = []
            for node_dict in result:
                node = Node(
                    uuid=UUID(hex=node_dict['uuid'], version=4),
                    public_address=IPAddress(node_dict['host']),
                )
                nodes.append(node)
            return nodes
        request.addCallback(to_nodes)

        return request

    def delete_container(self, name):
        request = self._request(
            b"DELETE", b"/configuration/containers/%s" % (
                name.encode('ascii'),
            ),
            None, {OK}
        )
        request.addCallback(lambda response: None)
        return request

    def this_node_uuid(self):
        getting_era = getProcessOutput(
            "flocker-node-era", reactor=self._reactor, env=environ)

        def got_era(era):
            return retry_failure(
                self._reactor, lambda: self._request(
                    b"GET", b"/state/nodes/by_era/" + era, None, {OK},
                    {NOT_FOUND: NotFound},
                ), [NotFound])
        request = getting_era.addCallback(got_era)
        request.addCallback(lambda result: UUID(result["uuid"]))
        return request


def conditional_create(client, reactor, condition, *args, **kwargs):
    """
    Create a dataset only if a certain condition is true for the
    configuration.

    This is useful for ensuring e.g. uniqueness of metadata across
    datasets. Conditional creation will be used to ensure that if the
    configuration changes the create won't happen; in this case the whole
    check-and-create will be retried, up to 20 times.

    All parameters are the same as
    ``IFlockerAPIV1Client.create_dataset_configuration`` except the
    following:

    :param client: ``IFlockerAPIV1Client`` provider.
    :param reactor: ``IReactorTime`` provider.
    :param condition: Callable which will be called with the current
        ``DatasetsConfiguration`` retrieved from the server. If this
        raises an exception then the create will be aborted.

    :return: ``Deferred`` firing with resulting ``Dataset`` if creation
        succeeded, or the relevant exception if creation failed.
    """
    context = _LOG_CONDITIONAL_CREATE()

    def create():
        d = client.list_datasets_configuration()

        def got_config(config):
            condition(config)
            return deferLater(reactor, 0.001, context.run,
                              client.create_dataset,
                              *args, configuration_tag=config.tag,
                              **kwargs)
        d.addCallback(got_config)
        return d

    with context.context():
        result = DeferredContext(
            retry_failure(reactor, create, [ConfigurationChanged],
                          [0.001] * 19))
        result.addActionFinish()
        return result.result
