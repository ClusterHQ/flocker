# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Testing utilities for ``flocker.acceptance``.
"""
from datetime import timedelta
from functools import wraps
from json import dumps
from os import environ, close
from unittest import SkipTest, skipUnless
from uuid import uuid4, UUID
from socket import socket
from contextlib import closing
from tempfile import mkstemp

import yaml
import json
import ssl

from docker.tls import TLSConfig

from twisted.internet import defer
from twisted.web.http import OK, CREATED
from twisted.python.filepath import FilePath
from twisted.internet import reactor
from twisted.internet.error import ProcessTerminated
from twisted.internet.task import deferLater

from eliot import start_action, Message, write_failure
from eliot.twisted import DeferredContext

from treq import json_content, content, get, post

from pyrsistent import PClass, field, CheckedPVector, pmap

from ..control import (
    Application, AttachedVolume, DockerImage, Manifestation, Dataset,
)

from ..common import gather_deferreds, loop_until, timeout, retry_failure
from ..common.configuration import (
    extract_substructure, MissingConfigError, Optional
)
from ..common.runner import download, run_ssh

from ..control.httpapi import REST_API_PORT
from ..ca import treq_with_authentication, UserCredential
from ..testtools import random_name
from ..apiclient import FlockerClient, DatasetState
from ..node.backends import backend_loader
from ..node.script import get_api
from ..node import dockerpy_client, backends
from ..node.agents.blockdevice import _SyncToThreadedAsyncAPIAdapter
from ..provision import reinstall_flocker_from_package_source

from .node_scripts import SCRIPTS as NODE_SCRIPTS

try:
    from pymongo import MongoClient
    from pymongo.errors import PyMongoError
    PYMONGO_INSTALLED = True
except ImportError:
    PYMONGO_INSTALLED = False

__all__ = [
    'require_cluster',
    'MONGO_APPLICATION', 'MONGO_IMAGE', 'get_mongo_application',
    'create_application', 'create_attached_volume',
    'get_docker_client', 'ACCEPTANCE_TEST_TIMEOUT'
    ]


# GCE sometimes takes up to a minute and a half to do a single operation,
# safer to wait at least 5 minutes per test, as most tests have to do at
# least 2 operations in series (cleanup then run test).
ACCEPTANCE_TEST_TIMEOUT = timedelta(minutes=5)

require_mongo = skipUnless(
    PYMONGO_INSTALLED, "PyMongo not installed")


# XXX The MONGO_APPLICATION will have to be removed because it does not match
# the tutorial yml files, and the yml should be testably the same:
# https://clusterhq.atlassian.net/browse/FLOC-947
MONGO_APPLICATION = u"mongodb-example-application"
MONGO_IMAGE = u"clusterhq/mongodb"

DOCKER_PORT = 2376


# Sometimes the TCP connection to Docker containers get stuck somewhere.
# Unless we avoid having to wait the full TCP timeout period the test will
# definitely fail with a timeout error (after a long delay!).  Anywhere we're
# polling for a condition, it's better to time out quickly and retry instead of
# possibly getting stuck in this case.
SOCKET_TIMEOUT_FOR_POLLING = 2.0


class FailureToUpgrade(Exception):
    """
    Exception raised to indicate a failure to install a new version of Flocker.
    """


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
        # XXX Hardcoded certificate filenames mean that this will only work on
        # clusters where Docker is configured to use the Flocker certificates.
        client_cert=(get_path(b"user.crt"), get_path(b"user.key")),
        # Blows up if not set
        # (https://github.com/shazow/urllib3/issues/695):
        ssl_version=ssl.PROTOCOL_TLSv1,
        # Don't validate hostname, we don't generate it correctly, but
        # do verify certificate authority signed the server certificate:
        assert_hostname=False,
        verify=get_path(b"cluster.crt"))

    return dockerpy_client(
        base_url="https://{}:{}".format(address, DOCKER_PORT),
        tls=tls, timeout=100, version='1.21',
    )


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


def get_dataset_backend(test_case):
    """
    Get the volume backend the acceptance tests are running as.

    :param test_case: The ``TestCase`` running this unit test.

    :return BackendDescription: The configured backend.
    :raise SkipTest: if the backend is specified.
    """
    backend = environ.get("FLOCKER_ACCEPTANCE_VOLUME_BACKEND")
    if backend is None:
        raise SkipTest(
            "Set acceptance testing volume backend using the " +
            "FLOCKER_ACCEPTANCE_VOLUME_BACKEND environment variable.")
    return backend_loader.get(backend)


def get_backend_api(cluster_id):
    """
    Get an appropriate BackendAPI for the specified dataset backend.

    Note this is a backdoor that is useful to be able to interact with cloud
    APIs in tests. For many dataset backends this does not make sense, but it
    provides a convenient means to interact with cloud backends such as EBS or
    cinder.

    :param cluster_id: The unique cluster_id, used for backend APIs that
        require this in order to be constructed.
    """
    backend_config_filename = environ.get(
        "FLOCKER_ACCEPTANCE_TEST_VOLUME_BACKEND_CONFIG")
    if backend_config_filename is None:
        raise SkipTest(
            'This test requires the ability to construct an IBlockDeviceAPI '
            'in order to verify construction. Please set '
            'FLOCKER_ACCEPTANCE_TEST_VOLUME_BACKEND_CONFIG to a yaml filepath '
            'with the dataset configuration.')
    backend_name = environ.get("FLOCKER_ACCEPTANCE_VOLUME_BACKEND")
    if backend_name is None:
        raise SkipTest(
            "Set acceptance testing volume backend using the " +
            "FLOCKER_ACCEPTANCE_VOLUME_BACKEND environment variable.")
    if backend_name in ('loopback', 'zfs'):
        # XXX If we ever want to setup loopback acceptance tests running on the
        # same node as the tests themselves, we will want to adjust this.
        raise SkipTest(
            "The loopback backend API can't be used remotely.")
    backend_config_filepath = FilePath(backend_config_filename)
    full_backend_config = yaml.safe_load(
        backend_config_filepath.getContent())
    backend_config = full_backend_config.get(backend_name)
    if 'backend' in backend_config:
        backend_config.pop('backend')
    backend = backend_loader.get(backend_name)
    return get_api(backend, pmap(backend_config), reactor, cluster_id)


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
    unsupported={backends.LOOPBACK},
    reason="doesn't support moving")


def skip_distribution(unsupported, reason):
    """
    Create decorator that skips a test if the distribution doesn't support the
    operations required by the test.

    :param supported: List of supported volume backends for this test.
    :param reason: The reason the backend isn't supported.
    """
    def decorator(test_method):
        """
        :param test_method: The test method that should be skipped.
        """
        @wraps(test_method)
        def wrapper(test_case, *args, **kwargs):
            distribution = environ.get("FLOCKER_ACCEPTANCE_DISTRIBUTION")
            if distribution in unsupported:
                raise SkipTest(
                    "Distribution not supported: "
                    "'{distribution}' ({reason}).".format(
                        distribution=distribution,
                        reason=reason,
                    )
                )
            return test_method(test_case, *args, **kwargs)
        return wrapper
    return decorator


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

    d = loop_until(reactor, create_mongo_client)
    return d


class ControlService(PClass):
    """
    A record of the cluster's control service.

    :ivar bytes public_address: The public address of the control service.
    """
    public_address = field(type=bytes)


class Node(PClass):
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

    def run_as_root(self, args, handle_stdout=None, handle_stderr=None):
        """
        Run a command on the node as root.

        :param args: Command and arguments to run.
        :param handle_stdout: Callable that will be called with lines parsed
            from the command stdout. By default logs an Eliot message.
        :param handle_stderr: Callable that will be called with lines parsed
            from the command stderr. By default logs an Eliot message.

        :return Deferred: Deferred that fires when the process is ended.
        """
        return run_ssh(reactor, "root", self.public_address, args,
                       handle_stdout=handle_stdout,
                       handle_stderr=handle_stderr)

    def reboot(self):
        """
        Reboot the node.
        """
        result = self.run_as_root([b"shutdown", b"-r", b"now"])
        # Reboot kills the SSH connection:
        result.addErrback(lambda f: f.trap(ProcessTerminated))
        return result

    def shutdown(self):
        """
        Shutdown the node.
        """
        result = self.run_as_root([b"shutdown", b"-h", b"now"])
        # Shutdown kills the SSH connection:
        result.addErrback(lambda f: f.trap(ProcessTerminated))
        return result

    def run_script(self, python_script, *argv):
        """
        Run a Python script as root on the node.

        :param python_script: Name of script in
            ``flocker.acceptance.node_scripts`` to run.
        :param argv: Additional arguments for the script.
        """
        script = NODE_SCRIPTS.child(python_script + ".py").getContent()
        return self.run_as_root([b"python2.7", b"-c", script] +
                                list(argv))


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

    def log_result(result, action):
        action.add_success_fields(result=_ensure_encodeable(result))
        return result

    @wraps(function)
    def wrapper(self, *args, **kwargs):

        serializable_args = tuple(_ensure_encodeable(a) for a in args)
        serializable_kwargs = {}
        for kwarg in kwargs:
            serializable_kwargs[kwarg] = _ensure_encodeable(kwargs[kwarg])

        context = start_action(
            action_type=label,
            args=serializable_args, kwargs=serializable_kwargs,
        )
        with context.context():
            d = DeferredContext(function(self, *args, **kwargs))
            d.addCallback(log_result, context)
            d.addActionFinish()
            return d.result
    return wrapper


def _ensure_encodeable(value):
    """
    Return a version of ``value`` that is guaranteed to be able to be logged.

    Catches ``TypeError``, which is raised for intrinsically unserializable
    values, and ``ValueError``, which catches ValueError, which is raised on
    circular references and also invalid dates.

    If normal encoding fails, return ``repr(value)``.
    """
    try:
        json.dumps(value)
    except (ValueError, TypeError):
        return repr(value)
    return value


class Cluster(PClass):
    """
    A record of the control service and the nodes in a cluster for acceptance
    testing.

    :ivar Node control_node: The node running the ``flocker-control``
        service.
    :ivar list nodes: The ``Node`` s in this cluster.

    :ivar treq: A ``treq`` client, eventually to be completely replaced by
        ``FlockerClient`` usage.
    :ivar reactor: A reactor to use to execute operations.
    :ivar client: A ``FlockerClient``.
    :ivar raw_distribution: Either a string with the distribution being run on
        the cluster or None if it is unknown.
    """
    control_node = field(mandatory=True, type=ControlService)
    nodes = field(mandatory=True, type=_NodeList)
    treq = field(mandatory=True)
    reactor = field(mandatory=True)
    client = field(type=FlockerClient, mandatory=True)
    certificates_path = field(FilePath, mandatory=True)
    cluster_uuid = field(mandatory=True, type=UUID)
    raw_distribution = field(mandatory=True, type=(bytes, type(None)))

    @property
    def distribution(self):
        """
        :returns: The name of the distribution installed on the cluster.
        :raises SkipTest: If the distribution was not set in environment
            variables.
        """
        if self.raw_distribution is None:
            raise SkipTest(
                'Set FLOCKER_ACCEPTANCE_DISTRIBUTION with the distribution '
                'that is installed on the nodes of the cluster.')
        return self.raw_distribution

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

        waiting = loop_until(reactor, deleted)
        waiting.addCallback(lambda _: deleted_dataset)
        return waiting

    @log_method
    def wait_for_dataset(self, expected_dataset):
        """
        Poll the dataset state API until the supplied dataset exists.

        :param Dataset expected_dataset: The configured dataset that
            we're waiting for in state.

        :returns: A ``Deferred`` which fires with the ``DatasetState`` of the
            cluster when the cluster state matches the configuration for the
            given dataset.
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
                actual_dataset_states = list(
                    d for d in results
                    if d.set('path', None) == expected_dataset_state)
                if actual_dataset_states:
                    return actual_dataset_states[0]
                else:
                    return None
            request.addCallback(got_results)
            return request

        waiting = loop_until(reactor, created)
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

        return loop_until(reactor, created)

    @log_method
    def current_nodes(self):
        """
        Get current nodes.

        :return: A ``Deferred`` firing with a tuple (cluster instance, API
            response).
        """
        request = self.treq.get(
            self.base_url + b"/state/nodes",
        )

        request.addCallback(check_and_decode_json, OK)
        return request

    @log_method
    def install_flocker_version(self, package_source,
                                destroy_persisted_state=False):
        """
        Change the version of flocker installed on all of the nodes to the
        version indicated by `package_source`.

        :param PackageSource package_source: The :class:`PackageSource` to
            install flocker from on all of the nodes.
        :param bool destroy_persisted_state: Whether to destroy the control
            node's state file when upgrading or not.
        """
        control_node_address = self.control_node.public_address
        all_cluster_nodes = set(list(x.public_address for x in self.nodes) +
                                [control_node_address])
        distribution = self.distribution

        def get_flocker_version():
            # Retry getting the flocker version for 10 times, with a 10 second
            # timeout on each. Flocker might not be running yet on the control
            # node when this is called.
            d = retry_failure(
                self.reactor,
                lambda: timeout(
                    self.reactor,
                    self.client.version(),
                    10
                ),
                [1]*10
            )
            d.addCallback(
                lambda v: v.get('flocker', u'').encode('ascii') or None)
            return d

        d = get_flocker_version()

        # If we fail to get the current version, assume we must reinstall
        # flocker. The following line consumes the error, and continues down
        # the callback chain of the deferred.
        d.addErrback(write_failure)

        def reinstall_if_needed(current_version):
            if (not current_version or
                    current_version != package_source.version):
                # If we did not get the version, or if the version does not
                # match the target version, then we must re-install flocker.
                return reinstall_flocker_from_package_source(
                    reactor, all_cluster_nodes, control_node_address,
                    package_source, distribution,
                    destroy_persisted_state=destroy_persisted_state)
            return current_version
        d.addCallback(reinstall_if_needed)

        d.addCallback(lambda _: get_flocker_version())

        def verify_version(current_version):
            if package_source.version:
                if current_version != package_source.version:
                    raise FailureToUpgrade(
                        "Failed to set version of flocker to %s, it is still "
                        "%s." % (package_source.version, current_version)
                    )
            return current_version
        d.addCallback(verify_version)

        return d

    @log_method
    def clean_nodes(self, remove_foreign_containers=True):
        """
        Clean containers and datasets via the API.

        :return: A `Deferred` that fires when the cluster is clean.
        """
        def api_clean_state(
            name, configuration_method, state_method, delete_method,
        ):
            """
            Clean entities from the cluster.

            :param unicode name: The name of the entities to clean.
            :param configuration_method: The function to obtain the configured
                entities.
            :param state_method: The function to get the current entities.
            :param delete_method: The method to delete an entity.

            :return: A `Deferred` that fires when the entities have been
                deleted.
            """
            context = start_action(
                action_type=u"acceptance:cleanup_" + name,
            )
            with context.context():
                get_items = DeferredContext(configuration_method())

                def delete_items(items):
                    return gather_deferreds(list(
                        delete_method(item)
                        for item in items
                    ))
                get_items.addCallback(delete_items)
                get_items.addCallback(
                    lambda ignored: loop_until(
                        reactor, lambda: state_method().addCallback(
                            lambda result: [] == result
                        )
                    )
                )
                return get_items.addActionFinish()

        def cleanup_all_containers(_):
            """
            Clean-up any containers run by Docker directly that are unmanaged
            by Flocker.
            """
            for node in self.nodes:
                client = get_docker_client(self, node.public_address)
                # Remove all existing containers on the node, in case
                # they're left over from previous test; they might e.g.
                # have a volume bind-mounted, preventing its destruction.
                for container in client.containers():
                    # Don't attempt to remove containers related to
                    # orchestration frameworks
                    protected_container = False
                    label_keys = container["Labels"].keys()
                    for key in label_keys:
                        if key.startswith("io.kubernetes."):
                            protected_container = True
                    if not protected_container:
                        client.remove_container(container["Id"], force=True)

        def cleanup_flocker_containers(_):
            cleaning_containers = api_clean_state(
                u"containers",
                self.configured_containers,
                self.current_containers,
                lambda item: self.remove_container(item[u"name"]),
            )
            return timeout(
                reactor, cleaning_containers, 30,
                Exception("Timed out cleaning up Flocker containers"),
            )

        def cleanup_datasets(_):
            cleaning_datasets = api_clean_state(
                u"datasets",
                self.client.list_datasets_configuration,
                self.client.list_datasets_state,
                lambda item: self.client.delete_dataset(item.dataset_id),
            )
            return timeout(
                reactor, cleaning_datasets, 180,
                Exception("Timed out cleaning up datasets"),
            )

        def cleanup_leases():
            context = start_action(action_type="acceptance:cleanup_leases")
            with context.context():
                get_items = DeferredContext(self.client.list_leases())

                def release_all(leases):
                    release_list = []
                    for lease in leases:
                        release_list.append(
                            self.client.release_lease(lease.dataset_id))
                    return gather_deferreds(release_list)

                get_items.addCallback(release_all)
                releasing_leases = get_items.addActionFinish()
                return timeout(
                    reactor, releasing_leases, 20,
                    Exception("Timed out cleaning up leases"),
                )

        def cleanup_volumes():
            try:
                api = get_backend_api(self.cluster_uuid)
            except SkipTest:
                # Can't clean up volumes if we don't have a backend api.
                return

            async_api = _SyncToThreadedAsyncAPIAdapter.from_api(api)

            def detach_and_destroy_volume(volume):
                d = async_api.detach_volume(volume.blockdevice_id)
                d.addBoth(
                    lambda _: async_api.destroy_volume(volume.blockdevice_id)
                )
                # Consume failures and write them out. Failures might just
                # indicate that the cluster beat us to deleting the volume
                # which should not cause the test to fail, we only want the
                # test to fail if list_volumes still returns a non-empty list.
                # The construction of api_clean_state should prevent this from
                # masking significant failures to clean up volumes.
                d.addErrback(write_failure)
                return d

            cleaning_volumes = api_clean_state(
                u"volumes",
                async_api.list_volumes,
                async_api.list_volumes,
                detach_and_destroy_volume,
            )
            return timeout(
                reactor, cleaning_volumes, 60,
                Exception("Timed out cleaning up volumes"),
            )

        d = DeferredContext(cleanup_leases())
        d.addCallback(cleanup_flocker_containers)
        if remove_foreign_containers:
            d.addCallback(cleanup_all_containers)
        d.addCallback(cleanup_datasets)
        d.addCallback(lambda _: cleanup_volumes())
        return d.result

    def get_file(self, node, path):
        """
        Retrieve the contents of a particular file on a particular node.

        :param Node node: The node on which to find the file.
        :param FilePath path: The path to the file on that node.
        """
        fd, name = mkstemp()
        close(fd)
        destination = FilePath(name)
        d = download(
            reactor=reactor,
            username=b"root",
            host=node.public_address.encode('ascii'),
            remote_path=path,
            local_path=destination,
        )
        d.addCallback(lambda ignored: destination)
        return d


def connected_cluster(
        reactor, control_node, certificates_path, num_agent_nodes,
        hostname_to_public_address, username='user',
):
    cluster_cert = certificates_path.child(b"cluster.crt")
    user_cert = certificates_path.child(
        "{}.crt".format(username).encode('ascii')
    )
    user_key = certificates_path.child(
        "{}.key".format(username).encode('ascii')
    )
    user_credential = UserCredential.from_files(user_cert, user_key)
    cluster = Cluster(
        control_node=ControlService(public_address=control_node),
        nodes=[],
        treq=treq_with_authentication(
            reactor, cluster_cert, user_cert, user_key),
        reactor=reactor,
        client=FlockerClient(reactor, control_node, REST_API_PORT,
                             cluster_cert, user_cert, user_key),
        certificates_path=certificates_path,
        cluster_uuid=user_credential.cluster_uuid,
        raw_distribution=environ.get('FLOCKER_ACCEPTANCE_DISTRIBUTION'),
    )

    # Wait until nodes are up and running:
    def nodes_available():
        Message.new(
            message_type="acceptance:testtools:cluster:polling",
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
        d.addCallbacks(lambda nodes: len(nodes) >= num_agent_nodes,
                       # Control service may not be up yet, keep trying:
                       failed_query)
        return d
    agents_connected = loop_until(reactor, nodes_available)

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
        "nodes", map(node_from_dict, nodes)))
    return agents_connected


def _get_test_cluster(reactor):
    """
    Build a ``Cluster`` instance.

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

    certificates_path = FilePath(
        environ["FLOCKER_ACCEPTANCE_API_CERTIFICATES_PATH"])

    hostname_to_public_address_env_var = environ.get(
        "FLOCKER_ACCEPTANCE_HOSTNAME_TO_PUBLIC_ADDRESS", "{}")
    hostname_to_public_address = json.loads(hostname_to_public_address_env_var)

    return connected_cluster(
        reactor,
        control_node,
        certificates_path,
        num_agent_nodes,
        hostname_to_public_address
    )


def require_cluster(num_nodes, required_backend=None,
                    require_container_agent=False):
    """
    A decorator which will call the supplied test_method when a cluster with
    the required number of nodes is available.

    :param int num_nodes: The number of nodes that are required in the cluster.

    :param required_backend: This optional parameter can be set to a
        ``BackendDescription`` in order to construct the requested backend
        for use in the test. This is done in a backdoor sort of manner, and is
        only for use by tests which want to interact with the specified backend
        in order to verify the acceptance test should pass. If this is set, the
        backend api will be sent as a keyword argument ``backend`` to the test,
        and the test will be skipped if the cluster is not set up for the
        specified backend.
    """
    def decorator(test_method):
        """
        :param test_method: The test method that will be called when the
            cluster is available and which will be supplied with the
            ``cluster``keyword argument.
        """
        def call_test_method_with_cluster(cluster, test_case, args, kwargs):
            kwargs['cluster'] = cluster
            if required_backend:
                backend_type = get_dataset_backend(test_case)
                if backend_type != required_backend:
                    raise SkipTest(
                        'This test requires backend type {} but is being run '
                        'on {}.'.format(required_backend.name,
                                        backend_type.name))
                kwargs['backend'] = get_backend_api(cluster.cluster_uuid)
            return test_method(test_case, *args, **kwargs)

        @wraps(test_method)
        def wrapper(test_case, *args, **kwargs):
            # Check that the required number of nodes are reachable and
            # clean them up prior to the test.  The nodes must already
            # have been started and their flocker services started before
            # we clean them.
            waiting_for_cluster = _get_test_cluster(reactor)

            def clean(cluster):
                existing = len(cluster.nodes)
                if num_nodes > existing:
                    raise SkipTest(
                        "This test requires a minimum of {necessary} nodes, "
                        "{existing} node(s) are set.".format(
                            necessary=num_nodes, existing=existing))
                return cluster.clean_nodes().addCallback(
                    # Limit nodes in Cluster to requested number:
                    lambda _: cluster.transform(
                        ["nodes"], lambda nodes: nodes[:num_nodes]))

            waiting_for_cluster.addCallback(clean)

            def enable_container_agent(cluster):
                # This should ideally be some sort of fixture/testresources
                # thing, but the APIs aren't quite right today.
                def configure_container_agent(node):
                    return ensure_container_agent_enabled(
                        node, require_container_agent)
                d = defer.gatherResults(
                    map(configure_container_agent, cluster.nodes),
                    consumeErrors=True)
                d.addCallback(lambda _: cluster)
                return d

            waiting_for_cluster.addCallback(enable_container_agent)
            calling_test_method = waiting_for_cluster.addCallback(
                call_test_method_with_cluster,
                test_case, args, kwargs
            )
            return calling_test_method
        return wrapper
    return decorator


def is_container_agent_running(node):
    """
    Check if the container agent is running on the specified node.

    :param Node node: the node to check.
    :return Deferred[bool]: a Deferred that will fire when
        with whether the container agent is runnning.
    """
    d = node.run_script("service_running", "flocker-container-agent")

    def not_existing(failure):
        failure.trap(ProcessTerminated)
        return False
    d.addCallbacks(lambda result: True, not_existing)
    return d


def set_container_agent_enabled_on_node(node, enabled):
    """
    Ensure the container agent is enabled/disabled as specified.

    :param Node node: the node on which to ensure the container
        agent's state
    :param bool enabled: True to ensure the container agent
        is enabled and running, false to ensure the opposite.
    :return Deferred[None]: a Deferred that will fire when
        the container agent is in the desired state.
    """
    if enabled:
        d = node.run_script("enable_service", "flocker-container-agent")
    else:
        d = node.run_script("disable_service", "flocker-container-agent")
    # If the agent was disabled We have to reboot to clear the control cache.
    # If we want to avoid the reboot we could add an API to do this.
    if not enabled:
        d.addCallback(lambda _: node.reboot())
        # Wait for reboot to be far enough along that everything
        # should be shutdown:
        d.addCallback(lambda _: deferLater(reactor, 20, lambda: None))
        # Wait until server is back up:
        d = d.addCallback(lambda _:
                          verify_socket(node.public_address, 22))
        d.addCallback(lambda _: loop_until(
            reactor, lambda: is_process_running(
                node, b'flocker-dataset-agent')))
        d.addCallback(
            lambda _:
            node.run_script("disable_service", "flocker-dataset-agent"))
        d.addCallback(
            lambda _:
            node.run_script("enable_service", "flocker-dataset-agent"))
        d.addCallback(lambda _: loop_until(
            reactor, lambda: is_process_running(
                node, b'flocker-dataset-agent')))
    # Hide the value in the callback as it could come from
    # different places and shouldn't be used.
    d.addCallback(lambda _: None)
    return d


def is_process_running(node, name):
    """
    Check if the process `name` is running on `node`.

    :param Node node: the node to check.
    :param bytes name: the name of the process to look for.
    :return Deferred[bool]: a deferred that will fire
        with whether at least one process named `name` is running
        on `node`.
    """
    # pidof will return the pid if the processes is
    # running else exit with status 1 which triggers the
    # errback chain.
    command = [b'pidof', b'-x', name]
    d = node.run_as_root(command)

    def not_existing(failure):
        failure.trap(ProcessTerminated)
        return False
    d.addCallbacks(lambda result: True, not_existing)
    return d


def ensure_container_agent_enabled(node, to_enable):
    """
    Ensure the container agent is enabled/disabled as specified.

    Doesn't make any changes if the agent is already in the
    desired state.

    :param Node node: the node on which to ensure the container
        agent's state
    :param bool to_enable: True to ensure the container agent
        is enabled and running, False to ensure the opposite.
    :return Deferred[None]: a Deferred that will fire when
        the container agent is in the desired state.
    """
    # If the agent is enabled but stopped, and the test
    # requests no container agent, then if the test rebooted
    # the node it would get a running container agent after
    # that point. This means that a test that fails in a
    # particular way could cause incorrect results in later
    # tests that rely on reboots. This function could change
    # to check the enabled status as well.
    d = is_container_agent_running(node)

    def change_if_needed(enabled):
        if enabled != to_enable:
            return set_container_agent_enabled_on_node(node, to_enable)
    d.addCallback(change_if_needed)
    return d


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
    parameters[u"command_line"] = [u"python2.7", u"-c",
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


def extract_external_port(
    client, container_identifier, internal_port
):
    """
    Inspect a running container for the external port number on which a
    particular internal port is exposed.

    :param docker.Client client: The Docker client to use to perform the
        inspect.
    :param unicode container_identifier: The unique identifier of the container
        to inspect.
    :param int internal_port: An internal, exposed port on the container.

    :return: The external port number on which ``internal_port`` from the
        container is exposed.
    :rtype: int
    """
    container_details = client.inspect_container(container_identifier)
    # If the container isn't running, this section is not present.
    network_settings = container_details[u"NetworkSettings"]
    ports = network_settings[u"Ports"]
    details = ports[u"{}/tcp".format(internal_port)]
    host_port = int(details[0][u"HostPort"])
    Message.new(
        message_type=u"acceptance:extract_external_port", host_port=host_port
    ).write()
    return host_port


def create_dataset(test_case, cluster, maximum_size=None, dataset_id=None,
                   metadata=None, node=None):
    """
    Create a dataset on a cluster (on its first node, specifically).

    :param TestCase test_case: The test the API is running on.
    :param Cluster cluster: The test ``Cluster``.
    :param int maximum_size: The size of the dataset to create on the test
        cluster.
    :param UUID dataset_id: The v4 UUID of the dataset.
        Generated if not specified.
    :param dict metadata: Metadata to be added to the create_dataset
        request.
    :param node: Node to create dataset on. By default first one in cluster.
    :return: ``Deferred`` firing with a ``flocker.apiclient.Dataset``
        dataset is present in actual cluster state.
    """
    if maximum_size is None:
        maximum_size = get_default_volume_size()
    if dataset_id is None:
        dataset_id = uuid4()
    if metadata is None:
        metadata = {}
    if node is None:
        node = cluster.nodes[0]
    configuring_dataset = cluster.client.create_dataset(
        node.uuid, maximum_size=maximum_size,
        dataset_id=dataset_id, metadata=metadata,
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
            s.settimeout(SOCKET_TIMEOUT_FOR_POLLING)
            conn = s.connect_ex((host, port))
            Message.new(
                message_type="acceptance:verify_socket",
                host=host,
                port=port,
                result=conn,
            ).write()
            return conn == 0

    dl = loop_until(reactor, can_connect)
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
            timeout=SOCKET_TIMEOUT_FOR_POLLING,
            persistent=False,
        )

        def failed(failure):
            Message.new(message_type=u"acceptance:http_query_failed",
                        reason=unicode(failure)).write()
            return False
        request.addCallbacks(content, failed)
        return request
    d = verify_socket(host, port)
    d.addCallback(lambda _: loop_until(reactor, lambda: make_post(
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
        timeout=SOCKET_TIMEOUT_FOR_POLLING,
        persistent=False,
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
            timeout=SOCKET_TIMEOUT_FOR_POLLING,
            persistent=False,
        )

        def failed(failure):
            Message.new(message_type=u"acceptance:http_query_failed",
                        reason=unicode(failure)).write()
            return False
        req.addCallbacks(content, failed)
        return req

    d = verify_socket(host, port)
    d.addCallback(lambda _: loop_until(reactor, query))
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


def acceptance_yaml_for_test(test_case):
    """
    Load configuration from a yaml file specified in an environment variable.

    Raises a SkipTest exception if the environment variable is not specified.
    """
    _ENV_VAR = 'ACCEPTANCE_YAML'
    filename = environ.get(_ENV_VAR)
    if not filename:
        test_case.skip(
            'Must set {} to an acceptance.yaml file ('
            'http://doc-dev.clusterhq.com/gettinginvolved/appendix.html#acceptance-testing-configuration'  # noqa
            ') plus additional keys in order to run this test.'.format(
                _ENV_VAR))
    with open(filename) as f:
        config = yaml.safe_load(f)
    return config


def extract_substructure_for_test(test_case, substructure, config):
    """
    Extract the keys from the config in substructure, which may be a nested
    dictionary.

    Raises a ``unittest.SkipTest`` if the substructure is not found in the
    configuration.

    This can be used to load credentials all at once for testing purposes.
    """
    try:
        return extract_substructure(config, substructure)
    except MissingConfigError as e:
        yaml.add_representer(
            Optional,
            lambda d, x: d.represent_scalar(u'tag:yaml.org,2002:str', repr(x)))
        test_case.skip(
            'Skipping test: could not get configuration: {}\n\n'
            'In order to run this test, add ensure file at $ACCEPTANCE_YAML '
            'has structure like:\n\n{}'.format(
                e.message,
                yaml.dump(substructure, default_flow_style=False))
        )
