# Copyright 2015 ClusterHQ Inc.  See LICENSE file for details.
"""
Operation to create a dataset.
"""

from functools import partial
from uuid import uuid4

from pyrsistent import PClass, field
from zope.interface import implementer

from flocker.common import loop_until

from .._interfaces import IProbe, IOperation


class EmptyClusterError(Exception):
    """
    Exception indicating that the cluster contains no nodes.
    """


@implementer(IProbe)
class CreateDatasetConvergenceProbe(PClass):

    reactor = field(mandatory=True)
    control_service = field(mandatory=True)
    primary = field(mandatory=True)
    dataset_id = field(mandatory=True)
    volume_size = field(mandatory=True)

    @classmethod
    def from_control_service(
        cls, reactor, control_service, dataset_id, volume_size
    ):
        d = control_service.list_nodes()

        def pick_primary(nodes):
            for node in nodes:
                return cls(
                    reactor=reactor,
                    control_service=control_service,
                    primary=node,
                    dataset_id=dataset_id,
                    volume_size=volume_size,
                )
            # Cannot proceed if there are no nodes in the cluster!
            raise EmptyClusterError("Cluster contains no nodes.")
        d.addCallback(pick_primary)

        return d

    def _converged(self, expected):
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
        d = self.control_service.create_dataset(
            primary=self.primary.uuid,
            maximum_size=self.volume_size,
            dataset_id=self.dataset_id,
        )

        def loop_until_converged(expected):
            return loop_until(
                self.reactor,
                partial(self._converged, expected)
            )
        d.addCallback(loop_until_converged)

        return d

    def cleanup(self):
        return self.control_service.delete_dataset(dataset_id=self.dataset_id)


@implementer(IOperation)
class CreateDatasetConvergence(object):

    def __init__(self, reactor, cluster, volume_size=None):
        self.reactor = reactor
        self.control_service = cluster.get_control_service(reactor)
        if volume_size is None:
            self.volume_size = cluster.default_volume_size()
        else:
            self.volume_size = volume_size

    def get_probe(self):
        return CreateDatasetConvergenceProbe.from_control_service(
            self.reactor, self.control_service, uuid4(), self.volume_size
        )
