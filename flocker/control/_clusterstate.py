# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Combine and retrieve current cluster state.
"""

from datetime import datetime, timedelta

from twisted.python.versions import Version
from twisted.python.deprecate import deprecated
from twisted.application.service import MultiService
from twisted.application.internet import TimerService

from pyrsistent import PRecord, field, pmap

from ._model import DeploymentState, ChangeSource


# Allowed inactivity period before updates are expired
EXPIRATION_TIME = timedelta(seconds=120)

v1_0 = Version("flocker", 1, 0, 0)


class _WiperAndSource(PRecord):
    """
    :ivar IClusterStateWipe wiper: A change wiper.
    :ivar IClusterStateSource source: Where the change wiper came from.
    """
    wiper = field()
    source = field()

    def last_activity(self):
        """
        Return the source's last activity time.
        """
        return self.source.last_activity()

    def update_cluster_state(self, deployment_state):
        """
        Update the state according to the wiper.
        """
        return self.wiper.update_cluster_state(deployment_state)


class ClusterStateService(MultiService):
    """
    Store known current cluster state, and combine partial updates with the
    existing known state.

    Data that hasn't been updated for ``EXPIRATION_TIME`` seconds is expired.
    Eventually we'll probably want a better policy:
    https://clusterhq.atlassian.net/browse/FLOC-1896

    :ivar DeploymentState _deployment_state: The current known cluster state.
    :ivar PMap _information_wipers: Map (wiper class, wiper key) to
        ``_WiperAndSource``.
    :ivar _clock: ``IReactorTime`` provider.
    """
    def __init__(self, reactor):
        MultiService.__init__(self)
        self._deployment_state = DeploymentState()
        timer = TimerService(1, self._wipe_expired)
        timer.clock = reactor
        timer.setServiceParent(self)
        self._information_wipers = pmap()
        self._clock = reactor

    def _wipe_expired(self):
        """
        Clear any expired state from memory.
        """
        current_time = datetime.utcfromtimestamp(self._clock.seconds())
        evolver = self._information_wipers.evolver()
        for key, wipe in self._information_wipers.items():
            last_activity = wipe.last_activity()
            if current_time - last_activity >= EXPIRATION_TIME:
                self._deployment_state = wipe.update_cluster_state(
                    self._deployment_state
                )
                evolver.remove(key)
        self._information_wipers = evolver.persistent()

    def manifestation_path(self, node_uuid, dataset_id):
        """
        Get the filesystem path of a manifestation on a particular node.

        :param UUID node_uuid: The uuid of the node.
        :param unicode dataset_id: The dataset identifier.

        :return FilePath: The path where the manifestation exists.
        """
        node = self._deployment_state.get_node(node_uuid)
        return node.paths[dataset_id]

    def as_deployment(self):
        """
        Return cluster state as a ``DeploymentState`` object.

        :return DeploymentState: Current state of the cluster.
        """
        return self._deployment_state

    def apply_changes_from_source(self, source, changes):
        """
        Apply some changes to the cluster state.

        :param IClusterChangeSource source: An object representing the entity
            that gave us these changes.  The information in the changes will be
            kept until they are overwritten or this entity goes away.
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
        for change in changes:
            wiper = change.get_information_wipe()
            key = (wiper.__class__, wiper.key())
            self._information_wipers = self._information_wipers.set(
                key, _WiperAndSource(wiper=wiper, source=source)
            )

    @deprecated(v1_0, "ClusterStateService.apply_changes_from_source")
    def apply_changes(self, changes):
        """
        Compatibility layer.  See and use ``apply_changes_from_source``.
        """
        source = ChangeSource()
        source.set_last_activity(self._clock.seconds())
        return self.apply_changes_from_source(source, changes)
