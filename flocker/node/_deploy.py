# Copyright ClusterHQ Inc.  See LICENSE file for details.
# -*- test-case-name: flocker.node.test.test_deploy -*-

"""
Base interfaces for convergence agents.
"""

from uuid import UUID

from zope.interface import Interface, implementer, Attribute

from pyrsistent import PClass, field

from ..control._model import NodeState


class ILocalState(Interface):
    """
    An ``ILocalState`` is the result from discovering state. It must provide
    the state that will be sent to the control service, but can store
    additional state that is useful in calculate_changes.
    """

    def shared_state_changes():
        """
        Calculate the part of the local state that needs to be sent to the
        control service.

        :return: A tuple of ``IClusterStateChange`` providers that describe
            the local state that needs to be shared. These objects will be
            passed to the control service (see ``flocker.control._protocol``).
        """


@implementer(ILocalState)
class NodeLocalState(PClass):
    """
    An ``ILocalState`` that is comprised solely of a node_state which is shared
    with the control service.

    :ivar NodeState node_state: The current ``NodeState`` of this node.
    """
    node_state = field(type=NodeState, mandatory=True)

    def shared_state_changes(self):
        """
        The node_state is shared in this implementation of ``ILocalState``.
        """
        return (self.node_state,)


class IDeployer(Interface):
    """
    An object that can discover local state and calculate necessary
    changes to bring local state and desired cluster configuration into
    alignment.

    :ivar UUID node_uuid: The UUID of the node this deployer is running.
    :ivar unicode hostname: The hostname (really, IP) of the node this
        deployer is managing.
    """
    node_uuid = Attribute("")
    hostname = Attribute("")

    def discover_state(cluster_state, persistent_state):
        """
        Discover the local state, i.e. the state which is exclusively under
        the purview of the convergence agent running this instance.

        :param DeploymentState cluster_state: The previously discovered state
            of the cluster. Information here should NOT be copied into the
            result; the return result should include only information
            discovered by this particular deployer.

        :param PersistentState persistent_state: The persisted non-discoverable
            state of the cluster. This includes association between entities
            that can't reliably be determined by inspecting the running system.

        :return: A ``Deferred`` which fires with a ``ILocalState``. The
            result of shared_state_changes() will be passed to the control
            service (see ``flocker.control._protocol``), and the entire opaque
            object will be passed to this object's ``calculate_changes()``
            method.
        """

    def calculate_changes(configuration, cluster_state, local_state):
        """
        Calculate the state changes necessary to make the local state match the
        desired cluster configuration.

        This is called in two situations:

        1. A real convergence iteration, in which case the local state is
           the immediately returned result of ``discover_state``.
        2. To discover whether to wake up the loop when it is sleeping if
           a new configuration or cluster state is received.

        Returning ``flocker.node.NoOp`` will result in the convergence
        loop sleeping for the duration of the specified sleep. If a new
        cluster state or configuration are received by the loop then it
        runs ``calculate_changes`` with cached local state and new
        configuration and cluster state in order to figure out whether it
        should interrupt the sleep. If this results in a ``IStateChange``
        or a ``NoOp`` with a shorter sleep duration then the sleep is
        appropriately curtailed (waking up immediately or with shorter
        delay respectively) and a real convergence iteration is run.

        :param Deployment configuration: The intended configuration of all
            nodes.

        :param DeploymentState cluster_state: The current state of all nodes
            already updated with recent output of ``discover_state``.

        :param ILocalState local_state: The ``ILocalState`` provider returned
            from the most recent call to ``discover_state``.

        :return: An ``IStateChange`` provider.
        """


class NotInUseDatasets(object):
    """
    Filter out datasets that are in use by applications on the current
    node.
    """
    def __init__(self, node_uuid, local_applications, leases):
        """
        :param UUID node_uuid: Node to check for datasets in use.
        :param applications: Applications running on the node.
        :param Leases leases: The current leases on datasets.
        """
        if local_applications is None:
            local_applications = []
        self._node_id = node_uuid
        self._in_use_datasets = {app.volume.manifestation.dataset_id
                                 for app in local_applications
                                 if app.volume is not None}
        self._leases = leases

    def __call__(self, objects,
                 get_dataset_id=lambda d: unicode(d.dataset_id)):
        """
        Filter out all objects whose dataset_id is in use.

        :param objects: Objects to filter.

        :param get_dataset_id: Callable to extract a unicode dataset ID
            from an object. By default looks up ``dataset_id`` attribute.

        :return list: Filtered objects.
        """
        result = []
        for obj in objects:
            u_dataset_id = get_dataset_id(obj)
            dataset_id = UUID(u_dataset_id)
            if u_dataset_id in self._in_use_datasets:
                continue
            if dataset_id in self._leases:
                # If there's a lease on this node elsewhere we don't
                # consider it to be in use on this node:
                if self._leases[dataset_id].node_id == self._node_id:
                    continue
            result.append(obj)
        return result
