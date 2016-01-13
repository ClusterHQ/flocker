"""
Remote Filesystem deployer.
"""

from uuid import UUID

from pyrsistent import PClass, field, pmap_field

from zope.interface import Interface, implementer, provider

from eliot import ActionType

from twisted.python.filepath import FilePath
from twisted.internet.defer import succeed, fail
from twisted.python.constants import Names, NamedConstant

from .. import IStateChange, IDeployer

# XXX infrastructure that should probably be in shared module, not in
# blockdevice:
from .blockdevice import (
    IDatasetStateChangeFactory,
    TransitionTable, DoNothing, BlockDeviceCalculator,
)

from ...common.algebraic import TaggedUnionInvariant
from ...control import (
    Dataset, Manifestation, NodeState, NonManifestDatasets, ILocalState,
)


class RemoteFilesystem(PClass):
    """
    In general case probably can't tell if filesystem is already mounted
    elsewhere or not... so omit that information.
    """
    dataset_id = field(type=UUID)
    # If None, not mounted locally (though might be mounted remotely):
    local_mount_point = field(type=(None.__class__, FilePath))


class IRemoteFilesystemAPI(Interface):
    """
    Some assumptions:

    1. In the general case the remote filesystem server will not be able to
       know what volumes are attached where. So we basically have to have all
       nodes doing discovery of state as pertains themselves and others.

    2. Mount/unmount can only be run locally.

    3. Local mount points can only really be easily known by the backend
       implementation. Otherwise we have to do some quite difficult or
       perhaps impossible attempt to parse e.g. the output of ``mount``.
    """
    def list():
        """
        :return: List of ``RemoteFilesystem``.
        """

    def create(dataset_id, metadata):
        """
        Metadata can be used to pass custom options to creation.
        """

    def destroy(dataset_id):
        pass

    def mount(dataset_id, path):
        """
        Unlike IBlockDeviceAPI we assume mounting *must* happen on local
        machine, so need for compute instance ID or anything of the sort.
        """
        pass

    def unmount(dataset_id, path):
        pass


class DatasetStates(Names):
    """
    States that a ``Dataset`` can be in.
    """
    # Doesn't exist yet.
    NON_EXISTENT = NamedConstant()
    # Exists, but not mounted on this machine:
    NOT_MOUNTED = NamedConstant()
    # Mounted on this node
    MOUNTED = NamedConstant()
    # Deleted from the driver
    DELETED = NamedConstant()


class DiscoveredDataset(PClass):
    """
    Dataset as discovered by deployer.

    :ivar DatasetStates state: The state this dataset was determined to be in.
    :ivar FilePath mount_point: The absolute path to the location on the node
        where the dataset will be mounted.
    """
    state = field(
        invariant=lambda state: (state in DatasetStates.iterconstants(),
                                 "Not a valid state"),
        mandatory=True,
    )
    dataset_id = field(type=UUID, mandatory=True)
    mount_point = field(FilePath)

    __invariant__ = TaggedUnionInvariant(
        tag_attribute='state',
        attributes_for_tag={
            DatasetStates.NOT_MOUNTED: set(),
            DatasetStates.MOUNTED: {'mount_point'},
        },
    )


class DesiredDataset(PClass):
    """
    Dataset as requested by configuration and applications.
    """
    state = field(
        invariant=lambda state: (state in DatasetStates.iterconstants(),
                                 "Not a valid state"),
        mandatory=True,
    )
    dataset_id = field(type=UUID, mandatory=True)
    metadata = pmap_field(
        key_type=unicode,
        value_type=unicode,
    )
    mount_point = field(FilePath)

    __invariant__ = TaggedUnionInvariant(
        tag_attribute='state',
        attributes_for_tag={
            DatasetStates.NOT_MOUNTED: {"metadata"},
            DatasetStates.MOUNTED: {"mount_point", "metadata"},
            DatasetStates.DELETED: set(),
        },
    )


API_CHANGE = ActionType(u"remotefs:deployer:action", [], [])


@provider(IDatasetStateChangeFactory)
@implementer(IStateChange)
class _APICommon(PClass):
    @property
    def eliot_action(self):
        return API_CHANGE()

    def run(self, deployer):
        try:
            self._run(deployer.api)
            return succeed(None)
        except:
            return fail()


class Create(_APICommon):
    dataset_id = field()
    metadata = field()

    @classmethod
    def from_state_and_config(cls, discovered_dataset, desired_dataset):
        return cls(
            dataset_id=desired_dataset.dataset_id,
            metadata=desired_dataset.metadata,
        )

    def _run(self, api):
        api.create(self.dataset_id, self.metadata)


class Destroy(_APICommon):
    dataset_id = field()

    @classmethod
    def from_state_and_config(cls, discovered_dataset, desired_dataset):
        return cls(
            dataset_id=desired_dataset.dataset_id,
            metadata=desired_dataset.metadata,
        )

    def _run(self, api):
        api.destroy(self.dataset_id)


class Mount(_APICommon):
    dataset_id = field()
    mount_point = field()

    @classmethod
    def from_state_and_config(cls, discovered_dataset, desired_dataset):
        return cls(
            dataset_id=desired_dataset.dataset_id,
            mount_point=desired_dataset.mount_point,
        )

    def _run(self, api):
        api.mount(self.dataset_id, self.mount_point)


class Unmount(_APICommon):
    dataset_id = field()
    mount_point = field()

    @classmethod
    def from_state_and_config(cls, discovered_dataset, desired_dataset):
        return cls(
            dataset_id=desired_dataset.dataset_id,
            mount_point=discovered_dataset.mount_point,
        )

    def _run(self, api):
        api.unmount(self.dataset_id, self.mount_point)


Desired = Discovered = DatasetStates
DATASET_TRANSITIONS = TransitionTable.create({
    Desired.MOUNTED: {
        Discovered.NON_EXISTENT: Create,
        Discovered.NOT_MOUNTED: Mount,
        Discovered.MOUNTED: DoNothing,
    },
    Desired.NOT_MOUNTED: {
        Discovered.NON_EXISTENT: Create,
        Discovered.NOT_MOUNTED: DoNothing,
        Discovered.MOUNTED: Unmount,
    },
    Desired.DELETED: {
        Discovered.NON_EXISTENT: DoNothing,
        Discovered.NOT_MOUNTED: Destroy,
        Discovered.MOUNTED: Unmount,
    },
})
del Desired, Discovered

# Nothing particularly BlockDevice-specific about the class:
CALCULATOR = BlockDeviceCalculator(
    transitions=DATASET_TRANSITIONS, dataset_states=DatasetStates)


@implementer(ILocalState)
class LocalState(PClass):
    hostname = field(type=unicode, mandatory=True)
    node_uuid = field(type=UUID, mandatory=True)
    datasets = pmap_field(UUID, DiscoveredDataset)

    def shared_state_changes(self):
        """
        Returns the NodeState and the NonManifestDatasets of the local state.
        These are the only parts of the state that need to be sent to the
        control service.
        """
        # XXX The structure of the shared state changes reflects the model
        # currently used by the control service. However, that model doesn't
        # seem to actually match what any consumer wants.
        manifestations = {}
        paths = {}
        nonmanifest_datasets = {}

        for dataset in self.datasets.values():
            dataset_id = dataset.dataset_id
            if dataset.state == DatasetStates.MOUNTED:
                manifestations[unicode(dataset_id)] = Manifestation(
                    dataset=Dataset(
                        dataset_id=dataset_id,
                        maximum_size=None,
                    ),
                    primary=True,
                )
                paths[unicode(dataset_id)] = dataset.mount_point
            elif dataset.state == DatasetStates.NOT_MOUNTED:
                # XXX this is a problem; if it's mounted somewhere else
                # we'll stomp on each other...
                nonmanifest_datasets[unicode(dataset_id)] = Dataset(
                    dataset_id=dataset_id,
                    maximum_size=None,
                )

        return (
            NodeState(
                uuid=self.node_uuid,
                hostname=self.hostname,
                manifestations=manifestations,
                paths=paths,
                devices={},
                applications=None,
            ),
            NonManifestDatasets(
                datasets=nonmanifest_datasets
            ),
        )


@implementer(IDeployer)
class RemoteFilesystemDeployer(PClass):
    """
    A lot of code can probably be shared with BlockDeviceDeployer.
    """
    hostname = field(type=unicode, mandatory=True)
    node_uuid = field(type=UUID, mandatory=True)
    api = field(mandatory=True)
    mountroot = field(type=FilePath, initial=FilePath(b"/flocker"))

    def discover_state(self, node_state):
        datasets = {}

        for remotefs in self.api.list():
            if remotefs.local_mount_point is None:
                datasets[remotefs.dataset_id] = DiscoveredDataset(
                    state=DatasetStates.NOT_MOUNTED)
            else:
                datasets[remotefs.dataset_id] = DiscoveredDataset(
                    state=DatasetStates.MOUNTED,
                    mount_point=remotefs.local_mount_point)

        local_state = LocalState(
            node_uuid=self.node_uuid,
            hostname=self.hostname,
            datasets=datasets,
        )

        return succeed(local_state)

    def _calculate_desired_for_manifestation(self, manifestation):
        """
        Get the ``DesiredDataset`` corresponding to a given manifestation.

        :param Manifestation manifestation: The

        :return: The ``DesiredDataset`` corresponding to the given
            manifestation.
        """
        dataset_id = UUID(manifestation.dataset.dataset_id)
        if manifestation.dataset.deleted:
            return DesiredDataset(
                state=DatasetStates.DELETED,
                dataset_id=dataset_id,
            )
        else:
            return DesiredDataset(
                state=DatasetStates.MOUNTED,
                dataset_id=dataset_id,
                metadata=manifestation.dataset.metadata,
                mount_point=self._mountpath_for_dataset_id(
                    unicode(dataset_id)
                ),
            )

    def _calculate_desired_state(
        self, configuration, local_applications, local_datasets
    ):
        # XXX not bothering with NotInUse filtering
        this_node_config = configuration.get_node(
            self.node_uuid, hostname=self.hostname)

        return {
            UUID(manifestation.dataset.dataset_id):
            self._calculate_desired_for_manifestation(
                manifestation
            )
            for manifestation in this_node_config.manifestations.values()
        }

    def calculate_changes(self, configuration, cluster_state, local_state):
        # XXX duplicates BlockDeviceDeployer.calculate_changes
        local_node_state = cluster_state.get_node(self.node_uuid,
                                                  hostname=self.hostname)

        desired_datasets = self._calculate_desired_state(
            configuration=configuration,
            local_applications=local_node_state.applications,
            local_datasets=local_state.datasets,
        )

        return self.calculator.calculate_changes_for_datasets(
            discovered_datasets=local_state.datasets,
            desired_datasets=desired_datasets,
        )
