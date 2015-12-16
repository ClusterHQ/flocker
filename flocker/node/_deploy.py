# Copyright ClusterHQ Inc.  See LICENSE file for details.
# -*- test-case-name: flocker.node.test.test_deploy -*-

"""
Deploy applications on nodes.
"""

from itertools import chain
from warnings import warn
from uuid import UUID
from datetime import timedelta

from zope.interface import Interface, implementer, Attribute


from characteristic import attributes

from pyrsistent import PClass, field

from eliot import write_failure, Logger, start_action

from twisted.internet.defer import gatherResults

from . import IStateChange, in_parallel, sequentially

from ..control._model import (
    DatasetChanges, DatasetHandoff, NodeState, Manifestation, Dataset,
    ip_to_uuid,
    )
from ..volume._ipc import RemoteVolumeManager, standard_node
from ..volume._model import VolumeSize
from ..volume.service import VolumeName


_logger = Logger()


def _to_volume_name(dataset_id):
    """
    Convert dataset ID to ``VolumeName`` with ``u"default"`` namespace.

    To be replaced in https://clusterhq.atlassian.net/browse/FLOC-737 with
    real namespace support.

    :param unicode dataset_id: Dataset ID.

    :return: ``VolumeName`` with default namespace.
    """
    return VolumeName(namespace=u"default", dataset_id=dataset_id)


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
    :ivar float poll_interval: Number of seconds to delay between
        iterations of convergence loop that call ``discover_state()``, to
        reduce impact of polling external resources. The actual delay may
        be smaller if the convergence loop decides more work is necessary
        in order to converge.
    """
    node_uuid = Attribute("")
    hostname = Attribute("")
    poll_interval = Attribute("")

    def discover_state(local_state):
        """
        Discover the local state, i.e. the state which is exclusively under
        the purview of the convergence agent running this instance.

        :param NodeState local_state: The previously known state of this
            node. This may include information that this deployer cannot
            discover on its own. Information here should NOT be copied
            into the result; the return result should include only
            information discovered by this particular deployer.

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

        Returning ``flocker.node.NoOp`` will result in the convergence
        loop sleeping for the duration of ``poll_interval``. The sleep
        will only be interrupted by a new configuration/cluster state
        update from control service which would result in need to run some
        ``IStateChange``. Thus even if no immediate changes are needed if
        you want ``discover_state`` to be called more frequently than
        ``poll_interval`` you should not return ``NoOp``.

        :param Deployment configuration: The intended configuration of all
            nodes.

        :param DeploymentState cluster_state: The current state of all nodes
            already updated with recent output of ``discover_state``.

        :param ILocalState local_state: The ``ILocalState`` provider returned
            from the most recent call to ``discover_state``.

        :return: An ``IStateChange`` provider.
        """


def _eliot_system(part):
    return u"flocker:p2pdeployer:" + part


@implementer(IStateChange)
class CreateDataset(PClass):
    """
    Create a new locally-owned dataset.

    :ivar Dataset dataset: Dataset to create.
    """
    dataset = field(type=Dataset, mandatory=True)

    @property
    def eliot_action(self):
        return start_action(
            _logger, _eliot_system(u"createdataset"),
            dataset_id=self.dataset.dataset_id,
            maximum_size=self.dataset.maximum_size,
        )

    def run(self, deployer):
        volume = deployer.volume_service.get(
            name=_to_volume_name(self.dataset.dataset_id),
            size=VolumeSize(maximum_size=self.dataset.maximum_size)
        )
        return deployer.volume_service.create(volume)


@implementer(IStateChange)
@attributes(["dataset"])
class ResizeDataset(object):
    """
    Resize an existing locally-owned dataset.

    :ivar Dataset dataset: Dataset to resize.
    """
    @property
    def eliot_action(self):
        return start_action(
            _logger, _eliot_system(u"createdataset"),
            dataset_id=self.dataset.dataset_id,
            maximum_size=self.dataset.maximum_size,
        )

    def run(self, deployer):
        volume = deployer.volume_service.get(
            name=_to_volume_name(self.dataset.dataset_id),
            size=VolumeSize(maximum_size=self.dataset.maximum_size)
        )
        return deployer.volume_service.set_maximum_size(volume)


@implementer(IStateChange)
@attributes(["dataset", "hostname"])
class HandoffDataset(object):
    """
    A dataset handoff that needs to be performed from this node to another
    node.

    See :cls:`flocker.volume.VolumeService.handoff` for more details.

    :ivar Dataset dataset: The dataset to hand off.
    :ivar bytes hostname: The hostname of the node to which the dataset is
         meant to be handed off.
    """

    @property
    def eliot_action(self):
        return start_action(
            _logger, _eliot_system(u"handoff"),
            dataset_id=self.dataset.dataset_id,
            hostname=self.hostname,
        )

    def run(self, deployer):
        service = deployer.volume_service
        destination = standard_node(self.hostname)
        return service.handoff(
            service.get(_to_volume_name(self.dataset.dataset_id)),
            RemoteVolumeManager(destination))


@implementer(IStateChange)
@attributes(["dataset", "hostname"])
class PushDataset(object):
    """
    A dataset push that needs to be performed from this node to another
    node.

    See :cls:`flocker.volume.VolumeService.push` for more details.

    :ivar Dataset: The dataset to push.
    :ivar bytes hostname: The hostname of the node to which the dataset is
         meant to be pushed.
    """

    @property
    def eliot_action(self):
        return start_action(
            _logger, _eliot_system(u"push"),
            dataset_id=self.dataset.dataset_id,
            hostname=self.hostname,
        )

    def run(self, deployer):
        service = deployer.volume_service
        destination = standard_node(self.hostname)
        return service.push(
            service.get(_to_volume_name(self.dataset.dataset_id)),
            RemoteVolumeManager(destination))


@implementer(IStateChange)
class DeleteDataset(PClass):
    """
    Delete all local copies of the dataset.

    A better action would be one that deletes a specific manifestation
    ("volume" in flocker.volume legacy terminology). Unfortunately
    currently "remotely owned volumes" (legacy terminology), aka
    non-primary manifestations or replicas, are not exposed to the
    deployer, so we have to enumerate them here.

    :ivar Dataset dataset: The dataset to delete.
    """
    dataset = field(mandatory=True, type=Dataset)

    @property
    def eliot_action(self):
        return start_action(
            _logger, _eliot_system("delete"),
            dataset_id=self.dataset.dataset_id,
        )

    def run(self, deployer):
        service = deployer.volume_service
        d = service.enumerate()

        def got_volumes(volumes):
            deletions = []
            for volume in volumes:
                if volume.name.dataset_id == self.dataset.dataset_id:
                    deletions.append(service.pool.destroy(volume).addErrback(
                        write_failure, _logger, u"flocker:p2pdeployer:delete"))
            return gatherResults(deletions)
        d.addCallback(got_volumes)
        return d


class NotInUseDatasets(object):
    """
    Filter out datasets that are in use by applications on the current
    node.

    For now we delay things like deletion until we know applications
    aren't using the dataset, and also until there are no leases. Later on
    we'll switch the container agent to rely solely on leases, at which
    point we can rip out the logic related to Application objects. See
    https://clusterhq.atlassian.net/browse/FLOC-2732.
    """
    def __init__(self, node_uuid, local_applications, leases):
        """
        :param UUID node_uuid: Node to check for datasets in use.
        :param applications: Applications running on the node.
        :param Leases leases: The current leases on datasets.
        """
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


@implementer(IDeployer)
class P2PManifestationDeployer(object):
    """
    Discover and calculate changes for peer-to-peer manifestations (e.g. ZFS)
    on a node.

    :ivar unicode hostname: The hostname of the node that this is running on.
    :ivar VolumeService volume_service: The volume manager for this node.
    """
    poll_interval = timedelta(seconds=1.0)

    def __init__(self, hostname, volume_service, node_uuid=None):
        if node_uuid is None:
            # To be removed in https://clusterhq.atlassian.net/browse/FLOC-1795
            warn("UUID is required, this is for backwards compat with existing"
                 " tests only. If you see this in production code that's "
                 "a bug.", DeprecationWarning, stacklevel=2)
            node_uuid = ip_to_uuid(hostname)
        self.node_uuid = node_uuid
        self.hostname = hostname
        self.volume_service = volume_service

    def discover_state(self, local_state):
        """
        Discover local ZFS manifestations.
        """
        # Add real namespace support in
        # https://clusterhq.atlassian.net/browse/FLOC-737; for now we just
        # strip the namespace since there will only ever be one.
        volumes = self.volume_service.enumerate()

        def map_volumes_to_size(volumes):
            primary_manifestations = {}
            for volume in volumes:
                if volume.node_id == self.volume_service.node_id:
                    # FLOC-1240 non-primaries should be added in too
                    path = volume.get_filesystem().get_path()
                    primary_manifestations[path] = (
                        volume.name.dataset_id, volume.size.maximum_size)
            return primary_manifestations
        volumes.addCallback(map_volumes_to_size)

        def got_volumes(available_manifestations):
            manifestation_paths = {dataset_id: path for (path, (dataset_id, _))
                                   in available_manifestations.items()}

            manifestations = list(
                Manifestation(dataset=Dataset(dataset_id=dataset_id,
                                              maximum_size=maximum_size),
                              primary=True)
                for (dataset_id, maximum_size) in
                available_manifestations.values())

            return NodeLocalState(
                node_state=NodeState(
                    uuid=self.node_uuid,
                    hostname=self.hostname,
                    applications=None,
                    manifestations={manifestation.dataset_id: manifestation for
                                    manifestation in manifestations},
                    paths=manifestation_paths,
                    devices={},
                )
            )
        volumes.addCallback(got_volumes)
        return volumes

    def calculate_changes(self, configuration, cluster_state, local_state):
        """
        Calculate necessary changes to peer-to-peer manifestations.

        Datasets that are in use by applications cannot be deleted,
        handed-off or resized. See
        https://clusterhq.atlassian.net/browse/FLOC-1425 for leases, a
        better solution.
        """
        local_state = cluster_state.get_node(self.node_uuid)
        # We need to know applications (for now) to see if we should delay
        # deletion or handoffs. Eventually this will rely on leases instead.
        if local_state.applications is None:
            return sequentially(changes=[])
        phases = []

        not_in_use_datasets = NotInUseDatasets(
            node_uuid=self.node_uuid,
            local_applications=local_state.applications,
            leases=configuration.leases,
        )

        # Find any dataset that are moving to or from this node - or
        # that are being newly created by this new configuration.
        dataset_changes = find_dataset_changes(
            self.node_uuid, cluster_state, configuration)

        resizing = not_in_use_datasets(dataset_changes.resizing)
        if resizing:
            phases.append(in_parallel(changes=[
                ResizeDataset(dataset=dataset)
                for dataset in resizing]))

        going = not_in_use_datasets(dataset_changes.going,
                                    lambda d: d.dataset.dataset_id)
        if going:
            phases.append(in_parallel(changes=[
                HandoffDataset(dataset=handoff.dataset,
                               hostname=handoff.hostname)
                for handoff in going]))

        if dataset_changes.creating:
            phases.append(in_parallel(changes=[
                CreateDataset(dataset=dataset)
                for dataset in dataset_changes.creating]))

        deleting = not_in_use_datasets(dataset_changes.deleting)
        if deleting:
            phases.append(in_parallel(changes=[
                DeleteDataset(dataset=dataset)
                for dataset in deleting
                ]))
        return sequentially(changes=phases)


def find_dataset_changes(uuid, current_state, desired_state):
    """
    Find what actions need to be taken to deal with changes in dataset
    manifestations between current state and desired state of the cluster.

    XXX The logic here assumes the mountpoints have not changed,
    and will act unexpectedly if that is the case. See
    https://clusterhq.atlassian.net/browse/FLOC-351 for more details.

    XXX The logic here assumes volumes are never added or removed to
    existing applications, merely moved across nodes. As a result test
    coverage for those situations is not implemented. See
    https://clusterhq.atlassian.net/browse/FLOC-352 for more details.

    :param UUID uuid: The uuid of the node for which to find changes.

    :param Deployment current_state: The old state of the cluster on which the
        changes are based.

    :param Deployment desired_state: The new state of the cluster towards which
        the changes are working.

    :return DatasetChanges: Changes to datasets that will be needed in
         order to match desired configuration.
    """
    uuid_to_hostnames = {node.uuid: node.hostname
                         for node in current_state.nodes}
    desired_datasets = {node.uuid:
                        set(manifestation.dataset for manifestation
                            in node.manifestations.values())
                        for node in desired_state.nodes}
    current_datasets = {node.uuid:
                        set(manifestation.dataset for manifestation
                            # We pretend ignorance is equivalent to no
                            # datasets; this is wrong. See FLOC-2060.
                            in (node.manifestations or {}).values())
                        for node in current_state.nodes}
    local_desired_datasets = desired_datasets.get(uuid, set())
    local_desired_dataset_ids = set(dataset.dataset_id for dataset in
                                    local_desired_datasets)
    local_current_dataset_ids = set(dataset.dataset_id for dataset in
                                    current_datasets.get(uuid, set()))
    remote_current_dataset_ids = set()
    for dataset_node_uuid, current in current_datasets.items():
        if dataset_node_uuid != uuid:
            remote_current_dataset_ids |= set(
                dataset.dataset_id for dataset in current)

    # If a dataset exists locally and is desired anywhere on the cluster, and
    # the desired dataset is a different maximum_size to the existing dataset,
    # the existing local dataset should be resized before any other action
    # is taken on it.
    resizing = set()
    for desired in desired_datasets.values():
        for new_dataset in desired:
            if new_dataset.dataset_id in local_current_dataset_ids:
                for cur_dataset in current_datasets[uuid]:
                    if cur_dataset.dataset_id != new_dataset.dataset_id:
                        continue
                    if cur_dataset.maximum_size != new_dataset.maximum_size:
                        resizing.add(new_dataset)

    # Look at each dataset that is going to be running elsewhere and is
    # currently running here, and add a DatasetHandoff for it to `going`.
    going = set()
    for dataset_node_uuid, desired in desired_datasets.items():
        if dataset_node_uuid != uuid:
            try:
                hostname = uuid_to_hostnames[dataset_node_uuid]
            except KeyError:
                # Apparently we don't know NodeState for this
                # node. Hopefully we'll learn this information eventually
                # but until we do we can't proceed.
                continue
            for dataset in desired:
                if dataset.dataset_id in local_current_dataset_ids:
                    going.add(DatasetHandoff(
                        dataset=dataset, hostname=hostname))

    # For each dataset that is going to be hosted on this node and did not
    # exist previously, make sure that dataset is in `creating`.
    # Unfortunately the logic for "did not exist previously" is wrong; our
    # knowledge of other nodes' state may be lacking if they are
    # offline. See FLOC-2060.
    creating_dataset_ids = local_desired_dataset_ids.difference(
        local_current_dataset_ids | remote_current_dataset_ids)
    creating = set(dataset for dataset in local_desired_datasets
                   if dataset.dataset_id in creating_dataset_ids)

    deleting = set(dataset for dataset in chain(*desired_datasets.values())
                   if dataset.deleted)
    return DatasetChanges(going=going, deleting=deleting,
                          creating=creating, resizing=resizing)
