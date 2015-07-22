# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Testing infrastructure for integration tests.
"""

from twisted.trial.unittest import TestCase

from ..testtools import require_cluster, create_dataset
from ...testtools import random_name


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
    class IntegrationTests(TestCase):
        """
        Test that the given application can start and restart with Flocker
        datasets as volumes.
        """
        def _start_container(self, name, dataset_id, external_port, cluster):
            """
            Start a container with a volume.

            :param unicode name: The container name.
            :param unicode dataset_id: The dataset ID.
            :param cluster: The ``Cluster``.
            :param int external_port: External port to expose on the container.

            :return: ``Deferred`` that fires when the container has been
                started.
            """
            app = {
                u"name": name,
                u"node_uuid": cluster.nodes[0].uuid,
                u"image": image_name,
                u"ports": [{u"internal": internal_port,
                            u"external": external_port}],
                u'restart_policy': {u'name': u'never'},
                u"volumes": [{u"dataset_id": dataset_id,
                              u"mountpoint": volume_path.path}],
            }
            created = cluster.create_container(app)
            created.addCallback(lambda _: self.addCleanup(
                cluster.remove_container, name))
            return created

        @require_cluster(1)
        def test_start(self, cluster):
            """
            The specified application can be started with a Docker dataset
            configured as its volume.
            """
            host = cluster.nodes[0].public_address
            port = 12345
            creating_dataset = create_dataset(self, cluster)
            creating_dataset.addCallback(
                lambda dataset: self._start_container(random_name(self),
                                                      dataset[u"dataset_id"],
                                                      port, cluster))
            creating_dataset.addCallback(
                lambda _: insert_data(self, host, port))
            creating_dataset.addCallback(
                lambda _: assert_inserted(self, host, port))
            return creating_dataset

    return IntegrationTests

