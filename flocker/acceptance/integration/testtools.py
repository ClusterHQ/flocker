# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Testing infrastructure for integration tests.
"""
from docker.errors import NotFound as DockerNotFound
from pyrsistent import PClass, field
from twisted.internet.defer import DeferredLock
from twisted.internet.threads import deferToThread

from ..testtools import require_cluster, create_dataset, get_docker_client
from ...testtools import AsyncTestCase, random_name


DOCKER_CLIENT_LOCK = DeferredLock()


def deferToThreadWithLock(lock, f, *args, **kwargs):
    """
    Like ``deferToThread``, but acquires ``lock`` before calling ``f`` and
    releases the lock when ``f`` returns or raises.
    """
    locking = lock.acquire()

    def locked(lock):
        return deferToThread(f, *args, **kwargs)

    calling = locking.addCallback(locked)

    def called(result):
        lock.release()
        return result

    unlocking = calling.addBoth(called)
    return unlocking


class Container(PClass):
    """
    Perform asynchronous docker-py start and remove operations on a Docker
    container that has been created.
    Docker-py operations are performed in a threadpool and with a lock in case
    DockerClient is not thread safe.

    :attr DockerClient client: A DockerClient connected to a specific docker
        server endpoint.
    :attr container_id: The unique ID of the container to operate on.
    """
    client = field()
    container_id = field()

    def start(self):
        """
        :returns: A ``Deferred`` that fires when the docker API start call
            completes.
        """
        return deferToThreadWithLock(
            DOCKER_CLIENT_LOCK,
            self.client.start,
            container=self.container_id
        )

    def remove(self):
        """
        Forcefully remove the container, even if it is still running.

        :returns: A ``Deferred`` that fires when the docker API remove call
            completes.
        """
        return deferToThreadWithLock(
            DOCKER_CLIENT_LOCK,
            self.client.remove_container,
            self.container_id,
            force=True,
        )


def create_container(client, create_arguments):
    """
    Create a Docker container and return a ``Container`` with which to perform
    start and remove operations.

    :param DockerClient client: The DockerClient which will be used to create
        the container.
    :param dict create_arguments: Keyword arguments to pass to
        DockerClient.create_container.
    :returns: A ``Container``.
    """
    container_data = client.create_container(**create_arguments)
    container_id = container_data["Id"]
    return Container(
        client=client,
        container_id=container_id,
    )


def stateful_container_for_test(test, cluster, node, image_name,
                                dataset, internal_path, internal_port,
                                external_port):
    """
    Create and start a ``Container`` on ``node``.
    Clean it up when the ``test`` has completed.

    :param TestCase test: The test.
    :param Cluster cluster: The ``Cluster`` with certificates for
        authenticating with the docker daemon on ``node``.
    :param unicode image_name: A name of the Docker image to use.
    :param Dataset dataset: The mounted Flocker dataset to bind mount into the
        container.
    :param FilePath internal_path: The path inside the container where
        ``dataset`` will be mounted.
    :param int internal_port: The port inside the container where
        ``image_name`` listens.
    :param int external_port: A port on the ``node`` which will be mapped to
        the ``internal_port``.
    :returns: A ``Deferred``  that fires with a ``Container``.
    """
    client = get_docker_client(
        cluster,
        node.public_address
    )
    arguments = {
        u"name": random_name(test),
        u"image": image_name,
        u"host_config": client.create_host_config(
            binds=[
                u"{}:{}".format(
                    dataset.path.path,
                    internal_path.path
                ),
            ],
            port_bindings={internal_port: external_port},
            restart_policy={u'Name': u'never'},
        ),
        u"ports": [internal_port],
    }

    d = deferToThreadWithLock(
        DOCKER_CLIENT_LOCK,
        create_container,
        client=client,
        create_arguments=arguments
    )

    def try_cleanup(container):
        d = container.remove()
        # The container may have been deliberately removed in the test.
        d.addErrback(
            lambda failure: failure.trap(DockerNotFound)
        )
        return d

    def register_cleanup_and_start(container):
        test.addCleanup(try_cleanup, container)
        d = container.start()
        d.addCallback(lambda ignored_start_result: container)
        return d

    d.addCallback(register_cleanup_and_start)
    return d


def make_dataset_integration_testcase(image_name, volume_path, internal_port,
                                      insert_data, assert_inserted):
    """
    Create a ``TestCase`` that tests a particular container can
    successfully use Flocker datasets as volumes.

    :param unicode image_name: The image to run.
    :param FilePath volume_path: The path within the container where a
        volume should be mounted.
    :param int internal_port: The port the container listens on.
    :param insert_data: Callable that given test instance, host and port,
         connects using an appropriate client and inserts some
         data. Should return ``Deferred`` that fires on success.
    :param assert_inserted: Callable that given test instance, host and
         port asserts that data was inserted by ``insert_data``. Should
         return ``Deferred`` that fires on success.

    :return: ``TestCase`` subclass.
    """
    class IntegrationTests(AsyncTestCase):
        """
        Test that the given application can start and restart with Flocker
        datasets as volumes.
        """
        @require_cluster(1)
        def test_start(self, cluster):
            """
            The specified application can be started with a Docker dataset
            configured as its volume.

            This ensures a newly created dataset meets the requirements of
            the application being tested. For example, some Docker
            containers can require a completely empty volume, or one that
            is writeable by non-root users, etc..
            """
            node = cluster.nodes[0]
            port = 12345
            creating_dataset = create_dataset(self, cluster)

            def create_container(dataset):
                return stateful_container_for_test(
                    test=self,
                    cluster=cluster,
                    node=node,
                    image_name=image_name,
                    dataset=dataset,
                    internal_path=volume_path,
                    internal_port=internal_port,
                    external_port=port,
                )
            creating_container = creating_dataset.addCallbacks(
                create_container,
                self.fail,
            )

            def begin_insert_data(container):
                return insert_data(self, node.public_address, port)
            inserting_data = creating_container.addCallbacks(
                begin_insert_data,
                self.fail,
            )

            def check(ignored):
                return assert_inserted(
                    self, node.public_address, port
                )
            checking = inserting_data.addCallback(check)

            return checking

        @require_cluster(1)
        def test_restart(self, cluster):
            """
            The specified application can be started with a Docker dataset
            configured as its volume that has already been used by the
            same application previously.
            """
            datasets = []
            node = cluster.nodes[0]
            port = 12345
            another_port = 12366
            creating_dataset = create_dataset(self, cluster)

            def create_container(dataset):
                datasets.append(dataset)
                return stateful_container_for_test(
                    test=self,
                    cluster=cluster,
                    node=node,
                    image_name=image_name,
                    dataset=dataset,
                    internal_path=volume_path,
                    internal_port=internal_port,
                    external_port=port,
                )
            creating_container = creating_dataset.addCallbacks(
                create_container,
                self.fail,
            )

            def begin_insert_data(container):
                d = insert_data(self, node.public_address, port)
                d.addCallback(lambda ignored: container)
                return d
            inserting_data = creating_container.addCallbacks(
                begin_insert_data,
                self.fail,
            )

            def remove_container(container):
                return container.remove()
            removing_container = inserting_data.addCallbacks(
                remove_container,
                self.fail,
            )

            def create_another_container(ignored):
                [dataset] = datasets
                return stateful_container_for_test(
                    test=self,
                    cluster=cluster,
                    node=node,
                    image_name=image_name,
                    dataset=dataset,
                    internal_path=volume_path,
                    internal_port=internal_port,
                    external_port=another_port,
                )
            recreating = removing_container.addCallbacks(
                create_another_container,
                self.fail,
            )

            def check(container):
                return assert_inserted(self, node.public_address, another_port)
            checking = recreating.addCallback(check)

            return checking

    return IntegrationTests
