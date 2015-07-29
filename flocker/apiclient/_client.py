# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Client for the Flocker REST API.
"""

from uuid import UUID

from zope.interface import Interface

from pyrsistent import PClass, field, pmap_field


class Dataset(PClass):
    """
    A dataset in the configuration.
    """
    dataset_id = field(type=UUID)
    primary = field(type=UUID)
    maximum_size = field(type=int)
    deleted = field(type=bool)
    metadata = pmap_field(unicode, unicode)


class DatasetState(PClass):
    """
    The state of a dataset in the cluster.
    """
    dataset_id = field(type=UUID)
    primary = field(type=UUID)
    maximum_size = field(type=int)


class DatasetAlreadyExists(Exception):
    """
    The suggested dataset ID already exists.
    """


class IFlockerAPIV1(Interface):
    """
    The Flocker REST API, v1.
    """
    def create_dataset(primary, maximum_size, dataset_id=None, metadata=None):
        """
        Create a new dataset in the configuration.

        :return: ``Deferred`` firing with resulting ``Dataset``, or
            errbacking with ``DatasetAlreadyExists``.
        """

    def move_dataset(primary, dataset_id):
        """
        Move the dataset to a new location.

        :return: ``Deferred`` firing with resulting ``Dataset``.
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


@implementer(IFlockerAPIV1)
class FakeFlockerAPIV1(object):
    """
    Fake in-memory implementation of ``IFlockerAPIV1``.
    """
    def __init__(self):
        # self._configured_datasets
        # self._state_datasets

    # Interface methods manipulate the above

    def synchronize_state(self):
        """
        Copy configuration into state.
        """
        self._state_datasets = [DatasetState(...) for dataset in self._configured_datasets]

