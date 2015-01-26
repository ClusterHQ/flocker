# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Combine and retrieve current cluster state.
"""

from twisted.application.service import Service

from ._model import Deployment, Node


class ClusterStateService(Service):
    """
    Store known current cluster state, and combine partial updates with
    the existing known state.

    (Follow up issue will deal with semantics of expiring data, which
    should happen so stale information isn't stored. This needs some extra
    work for the agent resending state even when it doesn't change, etc..)
    """
    def __init__(self):
        self._nodes = {}

    def update_node_state(self, hostname, node_state):
        """
        Update the state of a given node.

        :param unicode hostname: The node's identifier.
        :param NodeState node_state: The state of the node.
        """
        self._nodes[hostname] = node_state

    def as_deployment(self):
        """
        Return cluster state as a Deployment object.
        """
        return Deployment(nodes=frozenset([
            Node(hostname=hostname,
                 applications=frozenset(
                     node_state.running + node_state.not_running))
            for hostname, node_state in self._nodes.items()]))
