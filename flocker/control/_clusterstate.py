# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Combine and retrieve current cluster state.
"""

from twisted.application.service import Service

from ._model import DeploymentState


class ClusterStateService(Service):
    """
    Store known current cluster state, and combine partial updates with
    the existing known state.

    https://clusterhq.atlassian.net/browse/FLOC-1269 will deal with
    semantics of expiring data, which should happen so stale information
    isn't treated as correct.

    https://clusterhq.atlassian.net/browse/FLOC-1542 will deal with
    NodeState that has manifestations or application set to ``None``; for
    now we assume all data is present in any given update.
    """
    def __init__(self):
        self._nodes = {}

    def update_node_state(self, node_state):
        """
        Update the state of a given node.

        XXX: Multiple nodes may report being primary for a dataset. Enforce
        consistency here. See https://clusterhq.atlassian.net/browse/FLOC-1303

        :param NodeState node_state: The state of the node.
        """
        self._nodes[node_state.hostname] = node_state

    def manifestation_path(self, hostname, dataset_id):
        """
        Get the filesystem path of a manifestation on a particular node.

        :param unicode hostname: The name of the host.
        :param unicode dataset_id: The dataset identifier.

        :return FilePath: The path where the manifestation exists.
        """
        return self._nodes[hostname].paths[dataset_id]

    def as_deployment(self):
        """
        Return cluster state as a ``DeploymentState`` object.

        :return DeploymentState: Current state of the cluster.
        """
        return DeploymentState(nodes=self._nodes.values())
