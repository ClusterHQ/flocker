# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Testing utilities for ``flocker.acceptance``.
"""
from functools import wraps
from json import dumps
from os import environ
from unittest import SkipTest, skipUnless
from uuid import uuid4

import json

from twisted.web.http import OK, CREATED
from twisted.python.filepath import FilePath
from twisted.python.constants import Names, NamedConstant
from twisted.python.procutils import which
from twisted.internet import reactor

from eliot import Logger, start_action, Message, write_failure
from eliot.twisted import DeferredContext

from treq import json_content, content

from pyrsistent import PRecord, field, CheckedPVector, pmap

from ..control import (
    Application, AttachedVolume, DockerImage, Manifestation, Dataset,
)

from ..common import gather_deferreds

from ..control.httpapi import REST_API_PORT
from ..ca import treq_with_authentication
from ..testtools import loop_until, random_name, REALISTIC_BLOCKDEVICE_SIZE


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
    'create_attached_volume'
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
    :ivar treq: A ``treq`` client.
    """
    control_node = field(mandatory=True, type=ControlService)
    nodes = field(mandatory=True, type=_NodeList)
    treq = field(mandatory=True)
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
    def configured_datasets(self):
        """
        Return the configured dataset state of the cluster.

        :return: ``Deferred`` firing with a list of dataset dictionaries,
            the configuration of the cluster.
        """
        request = self.treq.get(
            self.base_url + b"/configuration/datasets", persistent=False)
        request.addCallback(check_and_decode_json, OK)
        return request

    @log_method
    def datasets_state(self):
        """
        Return the actual dataset state of the cluster.

        :return: ``Deferred`` firing with a list of dataset dictionaries,
            the state of the cluster.
        """
        request = self.treq.get(
            self.base_url + b"/state/datasets", persistent=False)
        request.addCallback(check_and_decode_json, OK)
        return request

    @log_method
    def wait_for_dataset(self, dataset_properties):
        """
        Poll the dataset state API until the supplied dataset exists.

        :param dict dataset_properties: The attributes of the dataset that
            we're waiting for.
        :returns: A ``Deferred`` which fires with an API response when a
            dataset with the supplied properties appears in the cluster.
        """
        def created():
            """
            Check the dataset state list for the expected dataset.
            """
            request = self.datasets_state()

            def got_body(body):
                # State listing doesn't have metadata or deleted, but does
                # have unpredictable path.
                expected_dataset = dataset_properties.copy()
                del expected_dataset[u"metadata"]
                del expected_dataset[u"deleted"]
                for dataset in body:
                    try:
                        dataset.pop("path")
                    except KeyError:
                        # Non-manifest datasets don't have a path
                        pass
                return expected_dataset in body
            request.addCallback(got_body)
            return request

        waiting = loop_until(created)
        waiting.addCallback(lambda ignored: dataset_properties)
        return waiting

    @log_method
    def create_dataset(self, dataset_properties):
        """
        Create a dataset with the supplied ``dataset_properties``.

        :param dict dataset_properties: The properties of the dataset to
            create.
        :returns: A ``Deferred`` which fires with an API response when a
            dataset with the supplied properties has been persisted to the
            cluster configuration.
        """
        request = self.treq.post(
            self.base_url + b"/configuration/datasets",
            data=dumps(dataset_properties),
            headers={b"content-type": b"application/json"},
            persistent=False
        )

        request.addCallback(check_and_decode_json, CREATED)
        return request

    @log_method
    def update_dataset(self, dataset_id, dataset_properties):
        """
        Update a dataset with the supplied ``dataset_properties``.

        :param unicode dataset_id: The uuid of the dataset to be modified.
        :param dict dataset_properties: The properties of the dataset to
            create.
        :returns: A ``Deferred`` which fires with an API response when the
            dataset update has been persisted to the cluster configuration.
        """
        request = self.treq.post(
            self.base_url + b"/configuration/datasets/%s" % (
                dataset_id.encode('ascii'),
            ),
            data=dumps(dataset_properties),
            headers={b"content-type": b"application/json"},
            persistent=False
        )

        request.addCallback(check_and_decode_json, OK)
        return request

    @log_method
    def delete_dataset(self, dataset_id):
        """
        Delete a dataset.

        :param unicode dataset_id: The uuid of the dataset to be modified.

        :returns: A ``Deferred`` which fires with an API response when the
            dataset deletion has been persisted to the cluster configuration.
        """
        request = self.treq.delete(
            self.base_url + b"/configuration/datasets/%s" % (
                dataset_id.encode('ascii'),
            ),
            headers={b"content-type": b"application/json"},
            persistent=False
        )

        request.addCallback(check_and_decode_json, OK)
        return request

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

        def cleanup_containers():
            return api_clean_state(
                self.configured_containers,
                self.current_containers,
                lambda item: self.remove_container(item[u"name"]),
            )

        def cleanup_datasets():
            return api_clean_state(
                lambda: self.configured_datasets().addCallback(
                    lambda datasets: list(
                        dataset
                        for dataset
                        in datasets
                        if not dataset.get(u"deleted", False)
                    )
                ),
                self.datasets_state,
                lambda item: self.delete_dataset(item[u"dataset_id"]),
            )

        return cleanup_containers().addCallback(lambda _: cleanup_datasets())


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


def create_dataset(test_case, cluster,
                   maximum_size=REALISTIC_BLOCKDEVICE_SIZE):
    """
    Create a dataset on a cluster (on its first node, specifically).

    :param TestCase test_case: The test the API is running on.
    :param Cluster cluster: The test ``Cluster``.
    :param int maximum_size: The size of the dataset to create on the test
        cluster.
    :return: ``Deferred`` firing with a dataset state dictionary once the
        dataset is present in actual cluster state.
    """
    # Configure a dataset on node1
    requested_dataset = {
        u"primary": cluster.nodes[0].uuid,
        u"dataset_id": unicode(uuid4()),
        u"maximum_size": maximum_size,
        u"metadata": {u"name": u"my_volume"},
    }

    configuring_dataset = cluster.create_dataset(requested_dataset)

    # Wait for the dataset to be created
    waiting_for_create = configuring_dataset.addCallback(
        lambda dataset: cluster.wait_for_dataset(dataset)
    )

    return waiting_for_create
