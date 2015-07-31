# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Client for the Flocker REST API.
"""

from uuid import UUID, uuid4

from zope.interface import Interface, implementer

from pyrsistent import PClass, field, pmap_field, pmap

from twisted.internet.defer import succeed, fail


class Dataset(PClass):
    """
    A dataset in the configuration.

    :attr UUID primary: The node where the dataset should manifest.
    :attr int maximum_size: Size of new dataset, in bytes.
    :attr UUID dataset_id: The UUID of the dataset.
    :attr metadata: A mapping between unicode keys and values.
    :attr bool deleted: If true indicates this dataset should be deleted.
    """
    dataset_id = field(type=UUID)
    primary = field(type=UUID)
    maximum_size = field(type=int)
    deleted = field(type=bool)
    metadata = pmap_field(unicode, unicode)


class DatasetState(PClass):
    """
    The state of a dataset in the cluster.

    :attr UUID primary: The node where the dataset should manifest.
    :attr int maximum_size: Size of new dataset, in bytes.
    :attr UUID dataset_id: The UUID of the dataset.
    """
    dataset_id = field(type=UUID)
    primary = field(type=UUID)
    maximum_size = field(type=int)


class DatasetAlreadyExists(Exception):
    """
    The suggested dataset ID already exists.
    """


class IFlockerAPIV1Client(Interface):
    """
    The Flocker REST API v1 client.
    """
    def create_dataset(primary, maximum_size, dataset_id=None,
                       metadata=pmap()):
        """
        Create a new dataset in the configuration.

        :param UUID primary: The node where the dataset should manifest.
        :param int maximum_size: Size of new dataset, in bytes.
        :param dataset_id: If given, the UUID to use for the dataset.
        :param metadata: A mapping between unicode keys and values, to be
            stored as dataset metadata.

        :return: ``Deferred`` that fires after the configuration has been
            updated with resulting ``Dataset``, or errbacking with
            ``DatasetAlreadyExists``.
        """

    def move_dataset(primary, dataset_id):
        """
        Move the dataset to a new location.

        :param UUID primary: The node where the dataset should manifest.
        :param dataset_id: Which dataset to move.

        :return: ``Deferred`` that fires after the configuration has been
            updated with the resulting ``Dataset``.
        """

    def list_datasets_configuration():
        """
        Return the configured datasets.

        :return: ``Deferred`` firing with iterable of ``Dataset``.
        """

    def list_datasets_state():
        """
        Return the actual datasets in the cluster.

        :return: ``Deferred`` firing with iterable of ``DatasetState``.
        """


@implementer(IFlockerAPIV1Client)
class FakeFlockerClient(object):
    """
    Fake in-memory implementation of ``IFlockerAPIV1Client``.
    """
    def __init__(self):
        self._configured_datasets = pmap()
        self.synchronize_state()

    def create_dataset(self, primary, maximum_size, dataset_id=None,
                       metadata=pmap()):
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

    def move_dataset(self, primary, dataset_id):
        self._configured_datasets = self._configured_datasets.transform(
            [dataset_id, "primary"], primary)
        return succeed(self._configured_datasets[dataset_id])

    def list_datasets_configuration(self):
        return succeed(self._configured_datasets.values())

    def list_datasets_state(self):
        return succeed(self._state_datasets)

    def synchronize_state(self):
        """
        Copy configuration into state.
        """
        self._state_datasets = [
            DatasetState(dataset_id=dataset.dataset_id,
                         primary=dataset.primary,
                         maximum_size=dataset.maximum_size)
            for dataset in self._configured_datasets.values()]
        return succeed(None)
