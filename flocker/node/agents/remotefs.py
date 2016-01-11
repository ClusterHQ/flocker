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

from .. import IStateChange

# XXX infrastructure that should probably be in shared module, not in
# blockdevice:
from .blockdevice import (
    IDatasetStateChangeFactory, PollUntilAttached,
    TransitionTable, DoNothing, BlockDeviceCalculator,
)

from ...common.algebraic import TaggedUnionInvariant


class RemoteFilesystem(PClass):
    """
    In general case probably can't tell if filesystem is already mounted
    elsewhere or not... so omit that information.
    """
    dataset_id = field(type=UUID)
    # If None, not mounted locally:
    mount_point = field(type=(None.__class__, FilePath))


class IRemoteFilesystemAPI(Interface):
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
        Discovered.ATTACHED_ELSEWHERE: PollUntilAttached,
        Discovered.NON_MANIFEST: Mount,
        Discovered.MOUNTED: DoNothing,
    },
    Desired.NON_MANIFEST: {
        Discovered.NON_EXISTENT: Create,
        Discovered.ATTACHED_ELSEWHERE: DoNothing,
        Discovered.NON_MANIFEST: DoNothing,
        Discovered.MOUNTED: Unmount,
    },
    Desired.DELETED: {
        Discovered.NON_EXISTENT: DoNothing,
        Discovered.ATTACHED_ELSEWHERE: DoNothing,
        Discovered.NON_MANIFEST: Destroy,
        Discovered.MOUNTED: Unmount,
    },
})
del Desired, Discovered

# Nothing particularly BlockDevice-specific about the class:
CALCULATOR = BlockDeviceCalculator(
    transitions=DATASET_TRANSITIONS, dataset_states=DatasetStates)
