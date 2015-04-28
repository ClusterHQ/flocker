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

    :ivar DeploymentState _deployment_state: The current known cluster
        state.
    """
    def __init__(self):
        self._deployment_state = DeploymentState()

    def manifestation_path(self, hostname, dataset_id):
        """
        Get the filesystem path of a manifestation on a particular node.

        :param unicode hostname: The name of the host.
        :param unicode dataset_id: The dataset identifier.

        :return FilePath: The path where the manifestation exists.
        """
        node = self._deployment_state.get_node(hostname)
        return node.paths[dataset_id]

    def as_deployment(self):
        """
        Return cluster state as a ``DeploymentState`` object.

        :return DeploymentState: Current state of the cluster.
        """
        return self._deployment_state

    def apply_changes(self, changes):
        """
        Apply some changes to the cluster state.

        :param list changes: Some ``IClusterStateChange`` providers to use to
            update the internal cluster state.
        """
        # XXX: Multiple nodes may report being primary for a dataset. Enforce
        # consistency here. See
        # https://clusterhq.atlassian.net/browse/FLOC-1303
        for change in changes:
            self._deployment_state = change.update_cluster_state(
                self._deployment_state
            )
