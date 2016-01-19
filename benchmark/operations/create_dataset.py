# Copyright 2015 ClusterHQ Inc.  See LICENSE file for details.
"""
Operation to create a dataset.
"""

from functools import partial
from uuid import uuid4

from pyrsistent import PClass, field
from zope.interface import implementer

from flocker.common import loop_until

from benchmark._interfaces import IProbe, IOperation
from benchmark.operations._common import select_node


@implementer(IProbe)
class CreateDatasetProbe(PClass):
    """
    Probe to create a dataset and wait for it to be mounted.
    """

    reactor = field(mandatory=True)
    control_service = field(mandatory=True)
    primary = field(mandatory=True)
    dataset_id = field(mandatory=True)
    volume_size = field(mandatory=True)

    @classmethod
    def setup(cls, reactor, control_service, dataset_id, volume_size):
        """
        Create a probe.

        :param reactor: Twisted Reactor.
        :param control_service: Benchmark control service.
        :param UUID dataset_id: UUID for created dataset.
        :param int volume_size: Size of created volume, in bytes.
        :return: Deferred firing with a new probe.
        """
        # Select an arbitrary node to be the primary for the dataset.
        d = control_service.list_nodes().addCallback(select_node)

        # Create the CreateDatasetProbe instance.
        def create_probe(node):
            return cls(
                reactor=reactor,
                control_service=control_service,
                primary=node,
                dataset_id=dataset_id,
                volume_size=volume_size,
            )
        d.addCallback(create_probe)

        return d

    def _converged(self, expected):
        """
        Check whether a dataset has been created.

        :param flocker.apiclient.Dataset expected: A dataset to match against
            the results of ``list_datasets_state``.
        :return: a Deferred that fires True if the expected dataset exists in
            the cluster, or False otherwise.
        """
        d = self.control_service.list_datasets_state()

        def dataset_matches(inspecting, expected):
            return (
                expected.dataset_id == inspecting.dataset_id and
                expected.primary == inspecting.primary and
                inspecting.path is not None
            )

        def find_match(existing_state):
            return any(
                dataset_matches(state, expected) for state in existing_state
            )
        d.addCallback(find_match)
        return d

    def run(self):
        """
        Create a dataset, then wait for convergence.
        """
        d = self.control_service.create_dataset(
            primary=self.primary.uuid,
            maximum_size=self.volume_size,
            dataset_id=self.dataset_id,
        )

        def loop_until_converged(expected):
            return loop_until(self.reactor, partial(self._converged, expected))
        d.addCallback(loop_until_converged)

        return d

    def cleanup(self):
        """
        Delete the dataset created by the probe.
        """
        return self.control_service.delete_dataset(dataset_id=self.dataset_id)


@implementer(IOperation)
class CreateDataset(object):

    def __init__(self, reactor, cluster, volume_size=None):
        self.reactor = reactor
        self.control_service = cluster.get_control_service(reactor)
        if volume_size is None:
            self.volume_size = cluster.default_volume_size()
        else:
            self.volume_size = volume_size

    def get_probe(self):
        return CreateDatasetProbe.setup(
            self.reactor, self.control_service, uuid4(), self.volume_size
        )
