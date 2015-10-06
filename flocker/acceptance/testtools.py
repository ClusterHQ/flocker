# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Testing utilities for ``flocker.acceptance``.
"""
from functools import wraps
from json import dumps
from os import environ, close
from unittest import SkipTest, skipUnless
from uuid import uuid4
from socket import socket
from contextlib import closing
from tempfile import mkstemp

import json
import ssl

from docker import Client
from docker.tls import TLSConfig

from twisted.web.http import OK, CREATED
from twisted.python.filepath import FilePath
from twisted.python.constants import Names, NamedConstant
from twisted.python.procutils import which
from twisted.internet import reactor

from eliot import Logger, start_action, Message, write_failure
from eliot.twisted import DeferredContext

from treq import json_content, content, get, post

from pyrsistent import PRecord, field, CheckedPVector, pmap

from ..control import (
    Application, AttachedVolume, DockerImage, Manifestation, Dataset,
)

from ..common import gather_deferreds
from ..common.runner import download_file

from ..control.httpapi import REST_API_PORT
from ..ca import treq_with_authentication
from ..testtools import loop_until, random_name
from ..apiclient import FlockerClient, DatasetState

try:
    from pymongo import MongoClient
    from pymongo.errors import PyMongoError
    PYMONGO_INSTALLED = True
except ImportError:
    PYMONGO_INSTALLED = False

__all__ = [
    'require_cluster',
    'MONGO_APPLICATION', 'MONGO_IMAGE', 'get_mongo_application',
    'require_flocker_cli', 'create_application',
    'create_attached_volume', 'get_docker_client'
    ]

# XXX This assumes that the desired version of flocker-cli has been installed.
# Instead, the testing environment should do this automatically.
# See https://clusterhq.atlassian.net/browse/FLOC-901.
require_flocker_cli = skipUnless(which("flocker-deploy"),
                                 "flocker-deploy not installed")

require_mongo = skipUnless(
    PYMONGO_INSTALLED, "PyMongo not installed")


# XXX The MONGO_APPLICATION will have to be removed because it does not match
# the tutorial yml files, and the yml should be testably the same:
# https://clusterhq.atlassian.net/browse/FLOC-947
MONGO_APPLICATION = u"mongodb-example-application"
MONGO_IMAGE = u"clusterhq/mongodb"

DOCKER_PORT = 2376


def get_docker_client(cluster, address):
    """
    Open a Docker client to the given address.

    :param Cluster cluster: Description of the cluster we're talking to.
    :param bytes address: The public IP of the node to connect to.

    :return: Docker ``Client`` instance.
    """
    def get_path(name):
        return cluster.certificates_path.child(name).path

    tls = TLSConfig(
        client_cert=(get_path(b"user.crt"), get_path(b"user.key")),
        # Blows up if not set
        # (https://github.com/shazow/urllib3/issues/695):
        ssl_version=ssl.PROTOCOL_TLSv1,
        # Don't validate hostname, we don't generate it correctly, but
        # do verify certificate authority signed the server certificate:
        assert_hostname=False,
        verify=get_path(b"cluster.crt"))
    return Client(base_url="https://{}:{}".format(address, DOCKER_PORT),
                  tls=tls, timeout=100)


def get_mongo_application():
    """
    Return a new ``Application`` with a name and image corresponding to
    the MongoDB tutorial example:

    http://doc-dev.clusterhq.com/gettingstarted/tutorial/index.html
    """
    return Application(
        name=MONGO_APPLICATION,
        image=DockerImage.from_string(MONGO_IMAGE + u':latest'),
    )


def create_application(name, image, ports=frozenset(), volume=None,
                       links=frozenset(), environment=None, memory_limit=None,
                       cpu_shares=None):
    """
    Instantiate an ``Application`` with the supplied parameters and return it.
    """
    return Application(
        name=name, image=DockerImage.from_string(image + u':latest'),
        ports=ports, volume=volume, links=links, environment=environment,
        memory_limit=memory_limit, cpu_shares=cpu_shares
    )


def create_attached_volume(dataset_id, mountpoint, maximum_size=None,
                           metadata=pmap()):
    """
    Create an ``AttachedVolume`` instance with the supplied parameters and
    return it.

    :param unicode dataset_id: The unique identifier of the dataset of the
        attached volume.
    :param bytes mountpoint: The path at which the volume is attached.
    :param int maximum_size: An optional maximum size for the volume.

    :return: A new ``AttachedVolume`` instance referencing a primary
        manifestation of a dataset with the given unique identifier.
    """
    return AttachedVolume(
        manifestation=Manifestation(
            dataset=Dataset(
                dataset_id=dataset_id,
                maximum_size=maximum_size,
                metadata=metadata,
            ),
            primary=True,
        ),
        mountpoint=FilePath(mountpoint),
    )


# Highly duplicative of other constants.  FLOC-2584.
class DatasetBackend(Names):
    loopback = NamedConstant()
    zfs = NamedConstant()
    aws = NamedConstant()
    openstack = NamedConstant()


def get_dataset_backend(test_case):
    """
    Get the volume backend the acceptance tests are running as.

    :param test_case: The ``TestCase`` running this unit test.

    :return DatasetBackend: The configured backend.
    :raise SkipTest: if the backend is specified.
    """
    backend = environ.get("FLOCKER_ACCEPTANCE_VOLUME_BACKEND")
    if backend is None:
        raise SkipTest(
            "Set acceptance testing volume backend using the " +
            "FLOCKER_ACCEPTANCE_VOLUME_BACKEND environment variable.")
    return DatasetBackend.lookupByName(backend)


def skip_backend(unsupported, reason):
    """
    Create decorator that skips a test if the volume backend doesn't support
    the operations required by the test.

    :param supported: List of supported volume backends for this test.
    :param reason: The reason the backend isn't supported.
    """
    def decorator(test_method):
        """
        :param test_method: The test method that should be skipped.
        """
        @wraps(test_method)
        def wrapper(test_case, *args, **kwargs):
            backend = get_dataset_backend(test_case)

            if backend in unsupported:
                raise SkipTest(
                    "Backend not supported: {backend} ({reason}).".format(
                        backend=backend,
                        reason=reason,
                    )
                )
            return test_method(test_case, *args, **kwargs)
        return wrapper
    return decorator

require_moving_backend = skip_backend(
    unsupported={DatasetBackend.loopback},
    reason="doesn't support moving")


def get_default_volume_size():
    """
    :returns int: the default volume size (in bytes) supported by the
        backend the acceptance tests are using.
    """
    default_volume_size = environ.get("FLOCKER_ACCEPTANCE_DEFAULT_VOLUME_SIZE")
    if default_volume_size is None:
        raise SkipTest(
            "Set acceptance testing default volume size using the " +
            "FLOCKER_ACCEPTANCE_DEFAULT_VOLUME_SIZE environment variable.")
    return int(default_volume_size)


def get_mongo_client(host, port=27017):
    """
    Returns a ``Deferred`` which fires with a ``MongoClient`` when one has been
    created.

    See http://api.mongodb.org/python/current/api/pymongo/mongo_client.html#
        pymongo.mongo_client.MongoClient
    for more parameter information.

    :param bytes host: Hostname or IP address of the instance to connect to.
    :param int port: Port number on which to connect.

    The tutorial says "If you get a connection refused error try again after a
    few seconds; the application might take some time to fully start up."
    and so here we wait until the client can be created.
    """
    def create_mongo_client():
        try:
            client = MongoClient(host=host, port=port)
            client.areyoualive.posts.insert({"ping": 1})
            return client
        except PyMongoError:
            return False

    d = loop_until(create_mongo_client)
    return d


class ControlService(PRecord):
    """
    A record of the cluster's control service.

    :ivar bytes public_address: The public address of the control service.
    """
    public_address = field(type=bytes)


class Node(PRecord):
    """
    A record of a cluster node.

    :ivar bytes public_address: The public address of the node.
    :ivar bytes reported_hostname: The address of the node, as reported by the
        API.
    :ivar unicode uuid: The UUID of the node.
    """
    public_address = field(type=bytes)
    reported_hostname = field(type=bytes)
    uuid = field(type=unicode)


class _NodeList(CheckedPVector):
    """
    A list of nodes.

    See https://github.com/tobgu/pyrsistent/issues/26 for more succinct
    idiom combining this with ``field()``.
    """
    __type__ = Node


class ResponseError(ValueError):
    """
    An unexpected response from the REST API.
    """
    def __init__(self, code, body):
        ValueError.__init__(self, "Unexpected response code {}:\n{}\n".format(
            code, body))
        self.code = code


def check_and_decode_json(result, response_code):
    """
    Given ``treq`` response object, extract JSON and ensure response code
    is the expected one.

    :param result: ``treq`` response.
    :param int response_code: Expected response code.

    :return: ``Deferred`` firing with decoded JSON.
    """
    def error(body):
        raise ResponseError(result.code, body)

    if result.code != response_code:
        d = content(result)
        d.addCallback(error)
        return d

    return json_content(result)


def log_method(function):
    """
    Decorator that log calls to the given function.
    """
    label = "acceptance:" + function.__name__

    def log_result(result):
        Message.new(
            message_type=label + ":result",
            value=result,
        ).write()
        return result

    @wraps(function)
    def wrapper(self, *args, **kwargs):
        context = start_action(
            Logger(),
            action_type=label,
            args=args, kwargs=kwargs,
        )
        with context.context():
            d = DeferredContext(function(self, *args, **kwargs))
            d.addCallback(log_result)
            d.addActionFinish()
            return d.result
    return wrapper


class Cluster(PRecord):
    """
    A record of the control service and the nodes in a cluster for acceptance
    testing.

    :ivar Node control_node: The node running the ``flocker-control``
        service.
    :ivar list nodes: The ``Node`` s in this cluster.

    :ivar treq: A ``treq`` client, eventually to be completely replaced by
        ``FlockerClient`` usage.
    :ivar client: A ``FlockerClient``.
    """
    control_node = field(mandatory=True, type=ControlService)
    nodes = field(mandatory=True, type=_NodeList)
    treq = field(mandatory=True)
    client = field(type=FlockerClient, mandatory=True)
    certificates_path = field(FilePath, mandatory=True)

    @property
    def base_url(self):
        """
        :returns: The base url for API requests to this cluster's control
            service.
        """
        return b"https://{}:{}/v1".format(
            self.control_node.public_address, REST_API_PORT
        )

    @log_method
    def wait_for_deleted_dataset(self, deleted_dataset):
        """
        Poll the dataset state API until the supplied dataset does
        not exist.

        :param Dataset deleted_dataset: The configured dataset that
            we're waiting for to be removed from state.

        :returns: A ``Deferred`` which fires with ``expected_datasets``
            when the dataset is no longer found in state.
        """
        def deleted():
            request = self.client.list_datasets_state()

            def got_results(datasets):
                return deleted_dataset.dataset_id not in (
                    d.dataset_id for d in datasets)
            request.addCallback(got_results)
            return request

        waiting = loop_until(deleted)
        waiting.addCallback(lambda _: deleted_dataset)
        return waiting

    @log_method
    def wait_for_dataset(self, expected_dataset):
        """
        Poll the dataset state API until the supplied dataset exists.

        :param Dataset expected_dataset: The configured dataset that
            we're waiting for in state.

        :returns: A ``Deferred`` which fires with ``expected_datasets``
            when the cluster state matches the configuration for the given
            dataset.
        """
        expected_dataset_state = DatasetState(
            dataset_id=expected_dataset.dataset_id,
            primary=expected_dataset.primary,
            maximum_size=expected_dataset.maximum_size,
            path=None)

        def created():
            """
            Check the dataset state list for the expected dataset.
            """
            request = self.client.list_datasets_state()

            def got_results(results):
                # State has unpredictable path, so we don't bother
                # checking for its contents:
                actual_dataset_states = [d.set(path=None) for d in results]
                return expected_dataset_state in actual_dataset_states
            request.addCallback(got_results)
            return request

        waiting = loop_until(created)
        waiting.addCallback(lambda ignored: expected_dataset)
        return waiting

    @log_method
    def create_container(self, properties):
        """
        Create a container with the specified properties.

        :param dict properties: A ``dict`` mapping to the API request fields
            to create a container.

        :returns: A ``Deferred`` which fires with an API response when the
            container with the supplied properties has been persisted to the
            cluster configuration.
        """
        request = self.treq.post(
            self.base_url + b"/configuration/containers",
            data=dumps(properties),
            headers={b"content-type": b"application/json"},
            persistent=False
        )

        request.addCallback(check_and_decode_json, CREATED)
        return request

    @log_method
    def move_container(self, name, node_uuid):
        """
        Move a container.

        :param unicode name: The name of the container to move.
        :param unicode node_uuid: The UUID to which the container should
            be moved.
        :returns: A ``Deferred`` which fires with an API response when the
            container move has been persisted to the cluster configuration.
        """
        request = self.treq.post(
            self.base_url + b"/configuration/containers/" +
            name.encode("ascii"),
            data=dumps({u"node_uuid": node_uuid}),
            headers={b"content-type": b"application/json"},
            persistent=False
        )

        request.addCallback(check_and_decode_json, OK)
        return request

    @log_method
    def remove_container(self, name):
        """
        Remove a container.

        :param unicode name: The name of the container to remove.

        :returns: A ``Deferred`` which fires with an API response when the
            container removal has been persisted to the cluster configuration.
        """
        request = self.treq.delete(
            self.base_url + b"/configuration/containers/" +
            name.encode("ascii"),
            persistent=False
        )

        request.addCallback(check_and_decode_json, OK)
        return request

    @log_method
    def configured_containers(self):
        """
        Get current containers from configuration.

        :return: A ``Deferred`` firing with a tuple (cluster instance, API
            response).
        """
        request = self.treq.get(
            self.base_url + b"/configuration/containers",
            persistent=False
        )

        request.addCallback(check_and_decode_json, OK)
        return request

    @log_method
    def current_containers(self):
        """
        Get current containers.

        :return: A ``Deferred`` firing with a tuple (cluster instance, API
            response).
        """
        request = self.treq.get(
            self.base_url + b"/state/containers",
            persistent=False
        )

        request.addCallback(check_and_decode_json, OK)
        return request

    @log_method
    def wait_for_container(self, container_properties):
        """
        Poll the container state API until a container exists with all the
        supplied ``container_properties``.

        :param dict container_properties: The attributes of the container that
            we're waiting for. All the keys, values and those of nested
            dictionaries must match.
        :returns: A ``Deferred`` which fires with an API response when a
            container with the supplied properties appears in the cluster.
        """
        def created():
            """
            Check the container state list for the expected container
            properties.
            """
            request = self.current_containers()

            def got_response(containers):
                expected_container = container_properties.copy()
                for container in containers:
                    container_items = container.items()
                    if all([
                        item in container_items
                        for item in expected_container.items()
                    ]):
                        # Return cluster and container state
                        return container
                return False
            request.addCallback(got_response)
            return request

        return loop_until(created)

    @log_method
    def current_nodes(self):
        """
        Get current nodes.

        :return: A ``Deferred`` firing with a tuple (cluster instance, API
            response).
        """
        request = self.treq.get(
            self.base_url + b"/state/nodes",
            persistent=False
        )

        request.addCallback(check_and_decode_json, OK)
        return request

    def clean_nodes(self):
        """
        Clean containers and datasets via the API.

        :return: A `Deferred` that fires when the cluster is clean.
        """
        def api_clean_state(configuration_method, state_method, delete_method):
            """
            Clean entities from the cluster.

            :param configuration_method: The function to obtain the configured
                entities.
            :param state_method: The function to get the current entities.
            :param delete_method: The method to delete an entity.

            :return: A `Deferred` that fires when the entities have been
                deleted.
            """
            get_items = configuration_method()

            def delete_items(items):
                return gather_deferreds(list(
                    delete_method(item)
                    for item in items
                ))
            get_items.addCallback(delete_items)
            get_items.addCallback(
                lambda ignored: loop_until(
                    lambda: state_method().addCallback(
                        lambda result: [] == result
                    )
                )
            )
            return get_items

        def cleanup_containers(_):
            return api_clean_state(
                self.configured_containers,
                self.current_containers,
                lambda item: self.remove_container(item[u"name"]),
            )

        def cleanup_datasets(_):
            return api_clean_state(
                self.client.list_datasets_configuration,
                self.client.list_datasets_state,
                lambda item: self.client.delete_dataset(item.dataset_id),
            )

        def cleanup_leases():
            get_items = self.client.list_leases()

            def release_all(leases):
                release_list = []
                for lease in leases:
                    release_list.append(
                        self.client.release_lease(lease.dataset_id))
                return gather_deferreds(release_list)

            get_items.addCallback(release_all)
            return get_items

        d = cleanup_leases()
        d.addCallback(cleanup_containers)
        d.addCallback(cleanup_datasets)
        return d

    def get_file(self, node, path):
        """
        Retrieve the contents of a particular file on a particular node.

        :param Node node: The node on which to find the file.
        :param FilePath path: The path to the file on that node.
        """
        fd, name = mkstemp()
        close(fd)
        destination = FilePath(name)
        d = download_file(
            reactor, b"root", node.public_address, path, destination
        )
        d.addCallback(lambda ignored: destination)
        return d


def _get_test_cluster(reactor, node_count):
    """
    Build a ``Cluster`` instance with at least ``node_count`` nodes.

    :param int node_count: The number of nodes to ensure in the cluster.

    :returns: A ``Deferred`` which fires with a ``Cluster`` instance.
    """
    control_node = environ.get('FLOCKER_ACCEPTANCE_CONTROL_NODE')

    if control_node is None:
        raise SkipTest(
            "Set acceptance testing control node IP address using the " +
            "FLOCKER_ACCEPTANCE_CONTROL_NODE environment variable.")

    agent_nodes_env_var = environ.get('FLOCKER_ACCEPTANCE_NUM_AGENT_NODES')

    if agent_nodes_env_var is None:
        raise SkipTest(
            "Set the number of configured acceptance testing nodes using the "
            "FLOCKER_ACCEPTANCE_NUM_AGENT_NODES environment variable.")

    num_agent_nodes = int(agent_nodes_env_var)

    if num_agent_nodes < node_count:
        raise SkipTest("This test requires a minimum of {necessary} nodes, "
                       "{existing} node(s) are set.".format(
                           necessary=node_count, existing=num_agent_nodes))

    certificates_path = FilePath(
        environ["FLOCKER_ACCEPTANCE_API_CERTIFICATES_PATH"])
    cluster_cert = certificates_path.child(b"cluster.crt")
    user_cert = certificates_path.child(b"user.crt")
    user_key = certificates_path.child(b"user.key")
    cluster = Cluster(
        control_node=ControlService(public_address=control_node),
        nodes=[],
        treq=treq_with_authentication(
            reactor, cluster_cert, user_cert, user_key),
        client=FlockerClient(reactor, control_node, REST_API_PORT,
                             cluster_cert, user_cert, user_key),
        certificates_path=certificates_path,
    )

    hostname_to_public_address_env_var = environ.get(
        "FLOCKER_ACCEPTANCE_HOSTNAME_TO_PUBLIC_ADDRESS", "{}")
    hostname_to_public_address = json.loads(hostname_to_public_address_env_var)

    # Wait until nodes are up and running:
    def nodes_available():
        Message.new(
            message_type="acceptance:get_test_cluster:polling",
        ).write()

        def failed_query(failure):
            reasons = getattr(failure.value, 'reasons', None)
            if reasons is None:
                # Guess it was something else.  Do some simpler logging.
                write_failure(failure, logger=None)
            else:
                # It is one of those.  Log all of the stuff from inside it.
                for reason in reasons:
                    write_failure(reason, logger=None)
            return False
        d = cluster.current_nodes()
        d.addCallbacks(lambda nodes: len(nodes) >= node_count,
                       # Control service may not be up yet, keep trying:
                       failed_query)
        return d
    agents_connected = loop_until(nodes_available)

    # Extract node hostnames from API that lists nodes. Currently we
    # happen know these in advance, but in FLOC-1631 node identification
    # will switch to UUIDs instead.
    agents_connected.addCallback(lambda _: cluster.current_nodes())

    def node_from_dict(node):
        reported_hostname = node["host"]
        public_address = hostname_to_public_address.get(
            reported_hostname, reported_hostname)
        return Node(
            uuid=node[u"uuid"],
            public_address=public_address.encode("ascii"),
            reported_hostname=reported_hostname.encode("ascii"),
        )
    agents_connected.addCallback(lambda nodes: cluster.set(
        "nodes", map(node_from_dict, nodes[:node_count])))
    return agents_connected


def require_cluster(num_nodes):
    """
    A decorator which will call the supplied test_method when a cluster with
    the required number of nodes is available.

    :param int num_nodes: The number of nodes that are required in the cluster.
    """
    def decorator(test_method):
        """
        :param test_method: The test method that will be called when the
            cluster is available and which will be supplied with the
            ``cluster``keyword argument.
        """
        def call_test_method_with_cluster(cluster, test_case, args, kwargs):
            kwargs['cluster'] = cluster
            return test_method(test_case, *args, **kwargs)

        @wraps(test_method)
        def wrapper(test_case, *args, **kwargs):
            # get_clean_nodes will check that the required number of nodes are
            # reachable and clean them up prior to the test.
            # The nodes must already have been started and their flocker
            # services started.
            waiting_for_cluster = _get_test_cluster(
                reactor, node_count=num_nodes)

            def clean(cluster):
                return cluster.clean_nodes().addCallback(lambda _: cluster)

            waiting_for_cluster.addCallback(clean)
            calling_test_method = waiting_for_cluster.addCallback(
                call_test_method_with_cluster,
                test_case, args, kwargs
            )
            return calling_test_method
        return wrapper
    return decorator


def create_python_container(test_case, cluster, parameters, script,
                            cleanup=True, additional_arguments=()):
    """
    Create a Python container that runs a given script.

    :param TestCase test_case: The current test.
    :param Cluster cluster: The cluster to run on.
    :param dict parameters: Parameters for the ``create_container`` JSON
        query, beyond those provided by this function.
    :param FilePath script: Python code to run.
    :param bool cleanup: If true, remove container when test is over.
    :param additional_arguments: Additional arguments to pass to the
        script.

    :return: ``Deferred`` that fires when the configuration has been updated.
    """
    parameters = parameters.copy()
    parameters[u"image"] = u"python:2.7-slim"
    parameters[u"command_line"] = [u"python", u"-c",
                                   script.getContent().decode("ascii")] + list(
                                       additional_arguments)
    if u"restart_policy" not in parameters:
        parameters[u"restart_policy"] = {u"name": u"never"}
    if u"name" not in parameters:
        parameters[u"name"] = random_name(test_case)
    creating = cluster.create_container(parameters)

    def created(response):
        if cleanup:
            test_case.addCleanup(cluster.remove_container, parameters[u"name"])
        test_case.assertEqual(response, parameters)
        return response
    creating.addCallback(created)
    return creating


def create_dataset(test_case, cluster, maximum_size=None, dataset_id=None):
    """
    Create a dataset on a cluster (on its first node, specifically).

    :param TestCase test_case: The test the API is running on.
    :param Cluster cluster: The test ``Cluster``.
    :param int maximum_size: The size of the dataset to create on the test
        cluster.
    :param UUID dataset_id: The v4 UUID of the dataset.
        Generated if not specified.
    :return: ``Deferred`` firing with a ``flocker.apiclient.Dataset``
        dataset is present in actual cluster state.
    """
    if maximum_size is None:
        maximum_size = get_default_volume_size()
    if dataset_id is None:
        dataset_id = uuid4()

    configuring_dataset = cluster.client.create_dataset(
        cluster.nodes[0].uuid, maximum_size=maximum_size,
        dataset_id=dataset_id, metadata={u"name": u"my_volume"}
    )

    # Wait for the dataset to be created
    waiting_for_create = configuring_dataset.addCallback(
        lambda dataset: cluster.wait_for_dataset(dataset)
    )

    return waiting_for_create


def verify_socket(host, port):
    """
    Wait until the destination socket can be reached.

    :param bytes host: Host to connect to.
    :param int port: Port to connect to.

    :return Deferred: Firing when connection is possible.
    """
    def can_connect():
        with closing(socket()) as s:
            conn = s.connect_ex((host, port))
            Message.new(
                message_type="acceptance:verify_socket",
                host=host,
                port=port,
                result=conn,
            ).write()
            return conn == 0

    dl = loop_until(can_connect)
    return dl


def post_http_server(test, host, port, data, expected_response=b"ok"):
    """
    Make a POST request to an HTTP server on the given host and port
    and assert that the response body matches the expected response.

    :param bytes host: Host to connect to.
    :param int port: Port to connect to.
    :param bytes data: The raw request body data.
    :param bytes expected_response: The HTTP response body expected.
        Defaults to b"ok"
    """
    def make_post(host, port, data):
        request = post(
            "http://{host}:{port}".format(host=host, port=port),
            data=data,
            persistent=False
        )

        def failed(failure):
            Message.new(message_type=u"acceptance:http_query_failed",
                        reason=unicode(failure)).write()
            return False
        request.addCallbacks(content, failed)
        return request
    d = verify_socket(host, port)
    d.addCallback(lambda _: loop_until(lambda: make_post(
        host, port, data)))
    d.addCallback(test.assertEqual, expected_response)
    return d


def check_http_server(host, port):
    """
    Check if an HTTP server is running.

    Attempts a request to an HTTP server and indicate the success
    or failure of the request.

    :param bytes host: Host to connect to.
    :param int port: Port to connect to.

    :return Deferred: Fires with True if the request received a response,
            False if the request failed.
    """
    req = get(
        "http://{host}:{port}".format(host=host, port=port),
        persistent=False
    )

    def failed(failure):
        return False

    def succeeded(result):
        return True

    req.addCallbacks(succeeded, failed)
    return req


def query_http_server(host, port, path=b""):
    """
    Return the response from a HTTP server.

    We try multiple since it may take a little time for the HTTP
    server to start up.

    :param bytes host: Host to connect to.
    :param int port: Port to connect to.
    :param bytes path: Optional path and query string.

    :return: ``Deferred`` that fires with the body of the response.
    """
    def query():
        req = get(
            "http://{host}:{port}{path}".format(
                host=host, port=port, path=path),
            persistent=False
        )

        def failed(failure):
            Message.new(message_type=u"acceptance:http_query_failed",
                        reason=unicode(failure)).write()
            return False
        req.addCallbacks(content, failed)
        return req

    d = verify_socket(host, port)
    d.addCallback(lambda _: loop_until(query))
    return d


def assert_http_server(test, host, port,
                       path=b"", expected_response=b"hi"):

    """
    Assert that a HTTP serving a response with body ``b"hi"`` is running
    at given host and port.

    This can be coupled with code that only conditionally starts up
    the HTTP server via Flocker in order to check if that particular
    setup succeeded.

    :param bytes host: Host to connect to.
    :param int port: Port to connect to.
    :param bytes path: Optional path and query string.
    :param bytes expected_response: The HTTP response body expected.
        Defaults to b"hi"

    :return: ``Deferred`` that fires when assertion has run.
    """
    d = query_http_server(host, port, path)
    d.addCallback(test.assertEqual, expected_response)
    return d
