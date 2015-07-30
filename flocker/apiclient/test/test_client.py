# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for the Flocker REST API client.
"""

from uuid import uuid4

from bitmath import GiB

from zope.interface.verify import verifyObject

from twisted.trial.unittest import TestCase

from .._client import (
    IFlockerAPIV1, FakeFlockerAPIV1, Dataset,
)

DATASET_SIZE = int(GiB(1).to_Byte().value)


def make_clientv1_tests(client_factory, synchronize_state):
    """
    Create a ``TestCase`` for testing ``IFlockerAPIV1``.

    The presumption is that the state of datasets is completely under
    control of this process. So when testing a real client it will be
    talking to a in-process server.

    :param client_factory: 0-argument callable that returns a
        ``IFlockerAPIV1`` provider.

    :param synchronize_state: 0-argument callable that makes state match
        configuration.
    """
    class InterfaceTests(TestCase):
        def setUp(self):
            self.node_1 = uuid4()
            self.node_2 = uuid4()

        def test_interface(self):
            """
            The created client provides ``IFlockerAPIV1``.
            """
            client = client_factory()
            self.assertTrue(verifyObject(IFlockerAPIV1, client))

        def assert_creates(self, client, dataset_id=None, **create_kwargs):
            """
            Create a dataset and ensure it shows up in the configuration and
            return result of the ``create_dataset`` call.

            :param IFlockerAPIV1 client: Client to use.
            :param dataset_id: Dataset ID to use, or ``None`` if it should
                be generated.
            :param create_kwargs: Additional arguments to pass to
                ``create_dataset``.

            :return: ``Deferred`` firing with result of
                ``create_dataset``.
            """
            created = client.create_dataset(
                dataset_id=dataset_id, **create_kwargs)

            def got_result(dataset):
                if dataset_id is None:
                    expected_dataset_id = dataset.dataset_id
                else:
                    expected_dataset_id = dataset_id
                expected = Dataset(dataset_id=expected_dataset_id,
                                   **create_kwargs)
                self.assertEqual(expected, dataset)

                listed = client.list_datasets_configuration()
                listed.addCallback(
                    lambda result: self.assertIn(expected, result))
                listed.addCallback(lambda _: dataset)
                return listed

            created.addCallback(got_result)
            return created

        def test_create_assigns_dataset(self):
            """
            If no ``dataset_id`` is specified when calling ``create_dataset``,
            a new one is generated.
            """
            return self.assert_creates(client_factory(), primary=self.node_1,
                                       maximum_size=DATASET_SIZE)

        def test_create_given_dataset(self):
            """
            If no ``dataset_id`` is specified when calling ``create_dataset``,
            a new one is generated.
            """
            return self.assert_creates(client_factory(), primary=self.node_1,
                                       maximum_size=DATASET_SIZE,
                                       dataset_id=uuid4())

        def test_create_with_metadata(self):
            """
            The metadata passed to ``create_dataset`` is stored with the
            dataset.
            """
            return self.assert_creates(client_factory(), primary=self.node_1,
                                       maximum_size=DATASET_SIZE,
                                       metadata={u"hello": u"there"})

        # Create returns an error on conflicting dataset_id.

        # A created dataset is listed in the configuration.

        # A created dataset with custom dataset id is listed in the
        # configuration.

        # A created dataset with metadata is listed in the
        # configuration.

        # Move changes the primary of the dataset.

        # State returns information about state (uses
        # synchronize_state to populate expected information)

    return InterfaceTests


class FakeFlockerAPIV1Tests(
        make_clientv1_tests(FakeFlockerAPIV1,
                            lambda client: client.synchronize_state())):
    """
    Interface tests for ``FakeFlockerAPIV1``.
    """
