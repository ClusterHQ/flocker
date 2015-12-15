# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for ``flocker.node.agents.blockdevice``.
"""

from errno import ENOTDIR
from functools import partial
from os import getuid
import time
from uuid import UUID, uuid4
from subprocess import STDOUT, PIPE, Popen, check_output, check_call
from stat import S_IRWXU
from datetime import datetime

from bitmath import Byte, MB, MiB, GB, GiB

from pytz import UTC

import psutil

from characteristic import attributes

from zope.interface import implementer
from zope.interface.verify import verifyObject

from pyrsistent import (
    PClass, field, discard, pmap, pvector,
)

from hypothesis import given, note, assume
from hypothesis.strategies import (
    uuids, text, lists, just, integers, builds, sampled_from,
    dictionaries
)

from twisted.internet import reactor
from twisted.internet.defer import succeed
from twisted.python.components import proxyForInterface
from twisted.python.runtime import platform
from twisted.python.filepath import FilePath
from twisted.trial.unittest import SynchronousTestCase, SkipTest, TestCase

from eliot import start_action, write_traceback, Message, Logger
from eliot.testing import (
    validate_logging, capture_logging,
    LoggedAction, assertHasMessage, assertHasAction
)

from .. import blockdevice
from ...test.istatechange import make_istatechange_tests
from ..blockdevice import (
    BlockDeviceDeployerLocalState, BlockDeviceDeployer,
    BlockDeviceCalculator,

    IBlockDeviceAPI, MandatoryProfiles, IProfiledBlockDeviceAPI,
    BlockDeviceVolume, UnknownVolume, AlreadyAttachedVolume,
    CreateBlockDeviceDataset, UnattachedVolume, DatasetExists,
    UnmountBlockDevice, DetachVolume, AttachVolume,
    CreateFilesystem, DestroyVolume, MountBlockDevice, ActionNeeded,

    DATASET_TRANSITIONS, IDatasetStateChangeFactory,
    ICalculator,

    DiscoveredDataset, DesiredDataset, DatasetStates,

    PROFILE_METADATA_KEY,

    UNMOUNT_BLOCK_DEVICE,
    CREATE_BLOCK_DEVICE_DATASET,
    INVALID_DEVICE_PATH,
    CREATE_VOLUME_PROFILE_DROPPED,
    DISCOVERED_RAW_STATE,
    ATTACH_VOLUME,

    IBlockDeviceAsyncAPI,
    _SyncToThreadedAsyncAPIAdapter,
    allocated_size,
    ProcessLifetimeCache,
    FilesystemExists,
    UnknownInstanceID,
    get_blockdevice_volume,

    ICloudAPI,
    _SyncToThreadedAsyncCloudAPIAdapter,
)
from ..blockdevice_manager import BlockDeviceManager, IBlockDeviceManager

from ..loopback import (
    check_allocatable_size,
    LoopbackBlockDeviceAPI,
    _losetup_list_parse,
    _losetup_list, _blockdevicevolume_from_dataset_id,
    _backing_file_name,
)
from ....common.algebraic import tagged_union_strategy, merge_tagged_unions


from ... import run_state_change, in_parallel, ILocalState, NoOp, IStateChange
from ...testtools import (
    ideployer_tests_factory, to_node, assert_calculated_changes_for_deployer,
    compute_cluster_state,
    ControllableAction,
)
from ....testtools import (
    REALISTIC_BLOCKDEVICE_SIZE, run_process, make_with_init_tests, random_name,
    AsyncTestCase
)
from ....control import (
    Dataset, Manifestation, Node, NodeState, Deployment, DeploymentState,
    NonManifestDatasets, Application, AttachedVolume, DockerImage
)
from ....control._model import Leases

# Move these somewhere else, write tests for them. FLOC-1774
from ....common.test.test_thread import NonThreadPool, NonReactor
from ....common import (
    retry_failure, gather_deferreds, interface_decorator,
    RACKSPACE_MINIMUM_VOLUME_SIZE
)

CLEANUP_RETRY_LIMIT = 10
LOOPBACK_ALLOCATION_UNIT = int(MiB(1).to_Byte().value)
# Enough space for the ext4 journal:
LOOPBACK_MINIMUM_ALLOCATABLE_SIZE = int(MiB(16).to_Byte().value)

EMPTY_NODE_STATE = NodeState(uuid=uuid4(), hostname=u"example.com")

ARBITRARY_BLOCKDEVICE_ID = u'blockdevice_id_1'
ARBITRARY_BLOCKDEVICE_ID_2 = u'blockdevice_id_2'

# Eliot is transitioning away from the "Logger instances all over the place"
# approach. So just use this global logger for now.
_logger = Logger()


DISCOVERED_DATASET_STRATEGY = tagged_union_strategy(
    DiscoveredDataset,
    {
        'dataset_id': uuids(),
        'maximum_size': integers(min_value=1),
        'mount_point': builds(FilePath, sampled_from([
            '/flocker/abc', '/flocker/xyz',
        ])),
        'blockdevice_id': just(u''),  # This gets overriden below.
        'device_path': builds(FilePath, sampled_from([
            '/dev/xvdf', '/dev/xvdg',
        ])),
    }
).map(lambda dataset: dataset.set(
    blockdevice_id=_create_blockdevice_id_for_test(dataset.dataset_id),
))

DESIRED_DATASET_STRATEGY = tagged_union_strategy(
    DesiredDataset,
    {
        'dataset_id': uuids(),
        'maximum_size': integers(min_value=0).map(
            lambda n:
            LOOPBACK_MINIMUM_ALLOCATABLE_SIZE
            + n*LOOPBACK_ALLOCATION_UNIT),
        'metadata': dictionaries(keys=text(), values=text()),
        'mount_point': builds(FilePath, sampled_from([
            '/flocker/abc', '/flocker/xyz',
        ])),
    }
)


def dataset_map_from_iterable(iterable):
    """
    Turn a list of datasets into a map from their IDs to the datasets.
    """
    return {dataset.dataset_id: dataset
            for dataset in iterable}


if not platform.isLinux():
    # The majority of Flocker isn't supported except on Linux - this test
    # module just happens to run some code that obviously breaks on some other
    # platforms.  Rather than skipping each test module individually it would
    # be nice to have some single global solution.  FLOC-1560, FLOC-1205
    skip = "flocker.node.agents.blockdevice is only supported on Linux"


class _SizeInfo(PClass):
    """
    :ivar int actual: The number of bytes allocated in the filesystem to a
        file, as computed by counting block size.  A sparse file may have less
        space allocated to it than might be expected given just its reported
        size.
    :ivar int reported: The size of the file as a number of bytes, as computed
        by the apparent position of the end of the file (ie, what ``stat``
        reports).
    """
    actual = field(type=int, mandatory=True)
    reported = field(type=int, mandatory=True)


def get_size_info(api, volume):
    """
    Retrieve information about the size of the backing file for the given
    volume.

    :param LoopbackBlockDeviceAPI api: The loopback backend to use to retrieve
        the size information.
    :param BlockDeviceVolume volume: The volume the size of which to look up.

    :return: A ``_SizeInfo`` giving information about actual storage and
        reported size of the backing file for the given volume.
    """
    backing_file = api._root_path.descendant(
        ['unattached', _backing_file_name(volume)]
    )
    # Get actual number of 512 byte blocks used by the file.  See
    # http://stackoverflow.com/a/3212102
    backing_file.restat()
    actual = backing_file.statinfo.st_blocks * 512
    reported = backing_file.getsize()
    return _SizeInfo(actual=actual, reported=reported)


def make_filesystem(device, block_device):
    """
    Synchronously initialize a device file with an ext4 filesystem.

    :param FilePath device: The path to the file onto which to put the
        filesystem.  Anything accepted by ``mkfs`` is acceptable (including a
        regular file instead of a device file).
    :param bool block_device: If ``True`` then the device is expected to be a
        block device and the ``-F`` flag will not be passed to ``mkfs``.  If
        ``False`` then the device is expected to be a regular file rather than
        an actual device and ``-F`` will be passed to ``mkfs`` to force it to
        create the filesystem.  It's possible to detect whether the given file
        is a device file or not.  This flag is required anyway because it's
        about what the caller *expects*.  This is meant to provide an extra
        measure of safety (these tests run as root, this function potentially
        wipes the filesystem from the device specified, this could have bad
        consequences if it goes wrong).
    """
    options = []
    if block_device and not device.isBlockDevice():
        raise Exception(
            "{} is not a block device but it was expected to be".format(
                device.path
            )
        )
    elif device.isBlockDevice() and not block_device:
        raise Exception(
            "{} is a block device but it was not expected to be".format(
                device.path
            )
        )
    if not block_device:
        options.extend([
            # Force mkfs to make the filesystem even though the target is not a
            # block device.
            b"-F",
        ])
    command = [b"mkfs"] + options + [b"-t", b"ext4", device.path]
    run_process(command)


def mount(device, mountpoint):
    """
    Synchronously mount a filesystem.

    :param FilePath device: The path to the device file containing the
        filesystem.
    :param mountpoint device: The path to an existing directory at which to
        mount the filesystem.
    """
    run_process([b"mount", device.path, mountpoint.path])


def create_blockdevicedeployer(
    test_case, hostname=u"192.0.2.1", node_uuid=uuid4(),
    block_device_manager=BlockDeviceManager()
):
    """
    Create a new ``BlockDeviceDeployer``.

    :param unicode hostname: The hostname to assign the deployer.
    :param UUID node_uuid: The unique identifier of the node to assign the
        deployer.
    :param block_device_manager: The ``IBlockDeviceManager`` provider to use to
        interact with the OS when manipulating block devices.

    :return: The newly created ``BlockDeviceDeployer``.
    """
    api = loopbackblockdeviceapi_for_test(test_case)
    async_api = _SyncToThreadedAsyncAPIAdapter(
        _sync=api, _reactor=NonReactor(), _threadpool=NonThreadPool(),
    )
    return BlockDeviceDeployer(
        hostname=hostname,
        node_uuid=node_uuid,
        block_device_api=api,
        _async_block_device_api=async_api,
        mountroot=mountroot_for_test(test_case),
        block_device_manager=block_device_manager,
    )


def detach_destroy_volumes(api):
    """
    Detach and destroy all volumes known to this API.
    If we failed to detach a volume for any reason,
    sleep for 1 second and retry until we hit CLEANUP_RETRY_LIMIT.
    This is to facilitate best effort cleanup of volume
    environment after each test run, so that future runs
    are not impacted.
    """
    volumes = api.list_volumes()
    retry = 0
    action_type = u"agent:blockdevice:cleanup:details"
    with start_action(action_type=action_type):
        while retry < CLEANUP_RETRY_LIMIT and len(volumes) > 0:
            for volume in volumes:
                try:
                    if volume.attached_to is not None:
                        api.detach_volume(volume.blockdevice_id)
                    api.destroy_volume(volume.blockdevice_id)
                except:
                    write_traceback(_logger)

            time.sleep(1.0)
            volumes = api.list_volumes()
            retry += 1

        if len(volumes) > 0:
            Message.new(u"agent:blockdevice:failedcleanup:volumes",
                        volumes=volumes).write()


def delete_manifestation(node_state, manifestation):
    """
    Remove all traces of a ``Manifestation`` from a ``NodeState``.
    """
    dataset_id = manifestation.dataset.dataset_id
    node_state = node_state.transform(['manifestations', dataset_id], discard)
    node_state = node_state.transform(['paths', dataset_id], discard)
    node_state = node_state.transform(['devices', UUID(dataset_id)], discard)
    return node_state


class BlockDeviceDeployerLocalStateTests(SynchronousTestCase):
    """
    Tests for ``BlockDeviceDeployerLocalState``.
    """
    def setUp(self):
        self.node_uuid = uuid4()
        self.hostname = u"192.0.2.1"

    def test_provides_ilocalstate(self):
        """
        Verify that ``BlockDeviceDeployerLocalState`` instances provide the
        ILocalState interface.
        """
        local_state = BlockDeviceDeployerLocalState(
            node_uuid=self.node_uuid,
            hostname=self.hostname,
            datasets={},
        )
        self.assertTrue(
            verifyObject(ILocalState, local_state)
        )

    def test_shared_changes(self):
        """
        ``shared_state_changes`` returns a ``NodeState`` with
        the ``node_uuid`` and ``hostname`` from the
        ``BlockDeviceDeployerLocalState`` and a
        ``NonManifestDatasets``.
        """
        local_state = BlockDeviceDeployerLocalState(
            node_uuid=self.node_uuid,
            hostname=self.hostname,
            datasets={},
        )
        expected_changes = (
            NodeState(
                uuid=self.node_uuid,
                hostname=self.hostname,
                manifestations={},
                paths={},
                devices={},
                applications=None
            ),
            NonManifestDatasets(
                datasets={},
            )
        )
        self.assertEqual(
            local_state.shared_state_changes(),
            expected_changes,
        )

    def test_non_manifest_dataset(self):
        """
        When there is a dataset in the ``NON_MANIFEST`` state,
        it is reported as a non-manifest dataset.
        """
        dataset_id = uuid4()
        local_state = BlockDeviceDeployerLocalState(
            node_uuid=self.node_uuid,
            hostname=self.hostname,
            datasets={
                dataset_id: DiscoveredDataset(
                    state=DatasetStates.NON_MANIFEST,
                    dataset_id=dataset_id,
                    blockdevice_id=ARBITRARY_BLOCKDEVICE_ID,
                    maximum_size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE,
                ),
            },
        )
        expected_changes = (
            NodeState(
                uuid=self.node_uuid,
                hostname=self.hostname,
                manifestations={},
                paths={},
                devices={},
                applications=None
            ),
            NonManifestDatasets(
                datasets={
                    unicode(dataset_id): Dataset(
                        dataset_id=dataset_id,
                        maximum_size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE,
                    ),
                },
            )
        )
        self.assertEqual(
            local_state.shared_state_changes(),
            expected_changes,
        )

    def attached_dataset_test(self, state):
        """
        When there is a a dataset in the given attached state,
        it is reported as a non-manifest dataset.

        :param state: Either ``DatasetStates.ATTACHED`` or
            ``DatasetStates.ATTACHED_NO_FILESYSTEM``.
        """
        dataset_id = uuid4()
        local_state = BlockDeviceDeployerLocalState(
            node_uuid=self.node_uuid,
            hostname=self.hostname,
            datasets={
                dataset_id: DiscoveredDataset(
                    state=state,
                    dataset_id=dataset_id,
                    blockdevice_id=ARBITRARY_BLOCKDEVICE_ID,
                    maximum_size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE,
                    device_path=FilePath('/dev/xvdf'),
                ),
            },
        )
        expected_changes = (
            NodeState(
                uuid=self.node_uuid,
                hostname=self.hostname,
                manifestations={},
                paths={},
                devices={
                    dataset_id: FilePath('/dev/xvdf'),
                },
                applications=None
            ),
            NonManifestDatasets(
                datasets={
                    unicode(dataset_id): Dataset(
                        dataset_id=dataset_id,
                        maximum_size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE,
                    ),
                },
            )
        )
        self.assertEqual(
            local_state.shared_state_changes(),
            expected_changes,
        )

    def test_attached_dataset(self):
        """
        When there is a a dataset in the ``ATTACHED`` state,
        it is reported as a non-manifest dataset.
        """
        self.attached_dataset_test(DatasetStates.ATTACHED)

    def test_attached_no_filesystem_dataset(self):
        """
        When there is a a dataset in the ``ATTACHED_NO_FILESYSTEM`` state,
        it is reported as a non-manifest dataset.
        """
        self.attached_dataset_test(DatasetStates.ATTACHED_NO_FILESYSTEM)

    def test_mounted_dataset(self):
        """
        When there is a a dataset in the ``MOUNTED`` state,
        it is reported as a manifest dataset.
        """
        dataset_id = uuid4()
        mount_point = FilePath('/mount/point')
        device_path = FilePath('/dev/xvdf')
        local_state = BlockDeviceDeployerLocalState(
            node_uuid=self.node_uuid,
            hostname=self.hostname,
            datasets={
                dataset_id: DiscoveredDataset(
                    state=DatasetStates.MOUNTED,
                    dataset_id=dataset_id,
                    blockdevice_id=ARBITRARY_BLOCKDEVICE_ID,
                    maximum_size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE,
                    device_path=device_path,
                    mount_point=mount_point,
                ),
            },
        )
        expected_changes = (
            NodeState(
                uuid=self.node_uuid,
                hostname=self.hostname,
                manifestations={
                    unicode(dataset_id): Manifestation(
                        dataset=Dataset(
                            dataset_id=dataset_id,
                            maximum_size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE,
                        ),
                        primary=True,
                    )
                },
                paths={
                    unicode(dataset_id): mount_point
                },
                devices={
                    dataset_id: device_path,
                },
                applications=None
            ),
            NonManifestDatasets(),
        )
        self.assertEqual(
            local_state.shared_state_changes(),
            expected_changes,
        )


class BlockDeviceDeployerTests(
        ideployer_tests_factory(create_blockdevicedeployer)
):
    """
    Tests for ``BlockDeviceDeployer``.
    """


class BlockDeviceDeployerAsyncAPITests(SynchronousTestCase):
    """
    Tests for ``BlockDeviceDeployer.async_block_device_api``.
    """
    def test_default(self):
        """
        When not otherwise initialized, the attribute evaluates to a
        ``_SyncToThreadedAsyncAPIAdapter`` using the global reactor, the global
        reactor's thread pool, and the value of ``block_device_api``.
        """
        from twisted.internet import reactor
        threadpool = reactor.getThreadPool()

        api = UnusableAPI()
        deployer = BlockDeviceDeployer(
            hostname=u"192.0.2.1",
            node_uuid=uuid4(),
            block_device_api=api,
        )

        self.assertEqual(
            _SyncToThreadedAsyncAPIAdapter(
                _reactor=reactor, _threadpool=threadpool, _sync=api
            ),
            deployer.async_block_device_api,
        )

    def test_overridden(self):
        """
        The object ``async_block_device_api`` refers to can be overridden by
        supplying the ``_async_block_device_api`` keyword argument to the
        initializer.
        """
        api = UnusableAPI()
        async_api = _SyncToThreadedAsyncAPIAdapter(
            _reactor=NonReactor(), _threadpool=NonThreadPool(), _sync=api,
        )
        deployer = BlockDeviceDeployer(
            hostname=u"192.0.2.1",
            node_uuid=uuid4(),
            block_device_api=api,
            _async_block_device_api=async_api,
        )
        self.assertIs(async_api, deployer.async_block_device_api)


def assert_discovered_state(
    case,
    deployer,
    expected_discovered_datasets,
):
    """
    Assert that datasets on the state object returned by
    ``deployer.discover_state`` equals the given list of datasets.

    :param TestCase case: The running test.
    :param IDeployer deployer: The object to use to discover the state.
    :param expected_discovered_datasets: The expected discovered datasets.
        discover_state() is expected to return an
        ``BlockDeviceDeployerLocalState`` with a dataset attribute
        corresponding to this.
    :type expected_discovered_datasets: iterable of ``DiscoveredDataset``.

    :raise: A test failure exception if the manifestations are not what is
        expected.
    """
    previous_state = NodeState(
        uuid=deployer.node_uuid, hostname=deployer.hostname,
        applications=None, manifestations=None, paths=None,
        devices=None,
    )
    discovering = deployer.discover_state(previous_state)
    local_state = case.successResultOf(discovering)

    case.assertEqual(
        local_state,
        BlockDeviceDeployerLocalState(
            hostname=deployer.hostname,
            node_uuid=deployer.node_uuid,
            datasets=dataset_map_from_iterable(expected_discovered_datasets),
        )
    )


class BlockDeviceDeployerDiscoverRawStateTests(SynchronousTestCase):
    """
    Tests for ``BlockDeviceDeployer._discover_raw_state``.
    """

    def setUp(self):
        self.expected_hostname = u'192.0.2.123'
        self.expected_uuid = uuid4()
        self.api = loopbackblockdeviceapi_for_test(self)
        self.this_node = self.api.compute_instance_id()
        self.deployer = BlockDeviceDeployer(
            node_uuid=self.expected_uuid,
            hostname=self.expected_hostname,
            block_device_api=self.api,
            mountroot=mountroot_for_test(self),
        )

    def test_compute_instance_id(self):
        """
        ``BlockDeviceDeployer._discover_raw_state`` returns a ``RawState``
        with the ``compute_instance_id`` that the ``api`` reports.
        """
        raw_state = self.deployer._discover_raw_state()
        self.assertEqual(
            raw_state.compute_instance_id,
            self.api.compute_instance_id(),
        )

    def test_no_volumes(self):
        """
        ``BlockDeviceDeployer._discover_raw_state`` returns a
        ``RawState`` with empty ``volumes`` if the ``api`` reports
        no attached volumes.
        """
        raw_state = self.deployer._discover_raw_state()
        self.assertEqual(raw_state.volumes, [])

    def test_unattached_unmounted_device(self):
        """
        If a volume is attached but not mounted, it is included as a
        volume by ``BlockDeviceDeployer._discover_raw_state``.
        """
        unmounted = self.api.create_volume(
            dataset_id=uuid4(),
            size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE,
        )
        raw_state = self.deployer._discover_raw_state()
        self.assertEqual(raw_state.volumes, [
            unmounted,
        ])

    @capture_logging(assertHasMessage, DISCOVERED_RAW_STATE)
    def test_filesystem_state(self, logger):
        """
        ``RawState`` includes whether or not a volume has a filesystem.
        """
        with_fs = self.api.create_volume(
            dataset_id=uuid4(),
            size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE,
        )
        with_fs = self.api.attach_volume(with_fs.blockdevice_id,
                                         self.api.compute_instance_id())
        with_fs_device = self.api.get_device_path(with_fs.blockdevice_id)
        make_filesystem(with_fs_device, True)
        without_fs = self.api.create_volume(
            dataset_id=uuid4(),
            size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE,
        )
        without_fs = self.api.attach_volume(without_fs.blockdevice_id,
                                            self.api.compute_instance_id())
        without_fs_device = self.api.get_device_path(without_fs.blockdevice_id)
        devices_with_filesystems = self.deployer._discover_raw_state(
            ).devices_with_filesystems

        self.assertEqual(
            dict(
                with_fs=(
                    with_fs_device in devices_with_filesystems),
                without_fs=(
                    without_fs_device in devices_with_filesystems)),
            dict(
                with_fs=True,
                without_fs=False))


class BlockDeviceDeployerDiscoverStateTests(SynchronousTestCase):
    """
    Tests for ``BlockDeviceDeployer.discover_state``.
    """
    def setUp(self):
        self.expected_hostname = u'192.0.2.123'
        self.expected_uuid = uuid4()
        self.api = loopbackblockdeviceapi_for_test(self)
        self.this_node = self.api.compute_instance_id()
        self.deployer = BlockDeviceDeployer(
            node_uuid=self.expected_uuid,
            hostname=self.expected_hostname,
            block_device_api=self.api,
            mountroot=mountroot_for_test(self),
        )

    def test_no_devices(self):
        """
        ``BlockDeviceDeployer.discover_state`` returns a ``NodeState`` with
        empty ``manifestations`` if the ``api`` reports no locally attached
        volumes.
        """
        assert_discovered_state(self, self.deployer, [])

    def test_unattached_volume(self):
        volume = self.api.create_volume(
            dataset_id=uuid4(),
            size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE,
        )
        assert_discovered_state(
            self, self.deployer,
            expected_discovered_datasets=[
                DiscoveredDataset(
                    state=DatasetStates.NON_MANIFEST,
                    dataset_id=volume.dataset_id,
                    blockdevice_id=volume.blockdevice_id,
                    maximum_size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE,
                ),
            ],
        )

    def test_attached_unmounted_device(self):
        """
        If a volume is attached but not mounted, it is discovered as
        an ``ATTACHED`` dataset returned by
        ``BlockDeviceDeployer.discover_state``.
        """
        volume = self.api.create_volume(
            dataset_id=uuid4(),
            size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE,
        )
        self.api.attach_volume(
            volume.blockdevice_id,
            attach_to=self.this_node,
        )
        device_path = self.api.get_device_path(volume.blockdevice_id)
        make_filesystem(device_path, block_device=True)
        assert_discovered_state(
            self, self.deployer,
            expected_discovered_datasets=[
                DiscoveredDataset(
                    state=DatasetStates.ATTACHED,
                    dataset_id=volume.dataset_id,
                    blockdevice_id=volume.blockdevice_id,
                    maximum_size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE,
                    device_path=device_path,
                ),
            ],
        )

    def test_one_device(self):
        """
        ``BlockDeviceDeployer.discover_state`` returns a ``NodeState`` with one
        ``manifestations`` if the ``api`` reports one locally attached volume
        and the volume's filesystem is mounted in the right place.
        """
        dataset_id = uuid4()
        volume = self.api.create_volume(
            dataset_id=dataset_id,
            size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE,
        )
        self.api.attach_volume(
            volume.blockdevice_id,
            attach_to=self.this_node,
        )
        device = self.api.get_device_path(volume.blockdevice_id)
        mount_point = self.deployer.mountroot.child(bytes(dataset_id))
        mount_point.makedirs()
        make_filesystem(device, block_device=True)
        mount(device, mount_point)

        assert_discovered_state(
            self, self.deployer,
            expected_discovered_datasets=[
                DiscoveredDataset(
                    state=DatasetStates.MOUNTED,
                    dataset_id=volume.dataset_id,
                    blockdevice_id=volume.blockdevice_id,
                    maximum_size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE,
                    device_path=device,
                    mount_point=mount_point,
                ),
            ],
        )

    def test_attached_and_mismounted(self):
        """
        If a volume is attached and mounted but not mounted at the location
        ``BlockDeviceDeployer`` expects, the dataset returned by
        ``BlockDeviceDeployer.discover_state`` is marked as
        ``ATTACHED``.
        """
        # XXX: Presumably we should detect and repair this case,
        # so that the volume can be unmounted.
        volume = self.api.create_volume(
            dataset_id=uuid4(),
            size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE,
        )

        self.api.attach_volume(
            volume.blockdevice_id,
            attach_to=self.this_node,
        )

        device_path = self.api.get_device_path(
            volume.blockdevice_id,
        )
        make_filesystem(device_path, block_device=True)

        # Mount it somewhere beneath the expected mountroot (so that it is
        # cleaned up automatically) but not at the expected place beneath it.
        mountpoint = self.deployer.mountroot.child(b"nonsense")
        mountpoint.makedirs()
        mount(device_path, mountpoint)

        assert_discovered_state(
            self, self.deployer,
            expected_discovered_datasets=[
                DiscoveredDataset(
                    state=DatasetStates.ATTACHED,
                    dataset_id=volume.dataset_id,
                    blockdevice_id=volume.blockdevice_id,
                    maximum_size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE,
                    device_path=device_path,
                ),
            ],
        )

    def _incorrect_device_path_test(self, bad_value):
        """
        Assert that when ``IBlockDeviceAPI.get_device_path`` returns a value
        that must be wrong, the corresponding manifestation is not included in
        the discovered state for the node.
        """
        # XXX This discovers volumes as NON_MANIFEST, but we should
        # have a state so we can try to recover.
        volume = self.api.create_volume(
            dataset_id=uuid4(), size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE,
        )
        self.api.attach_volume(
            volume.blockdevice_id, self.api.compute_instance_id(),
        )

        # Break the API object now.
        self.patch(
            self.api, "get_device_path", lambda blockdevice_id: bad_value
        )

        assert_discovered_state(
            self, self.deployer,
            expected_discovered_datasets=[
                DiscoveredDataset(
                    state=DatasetStates.NON_MANIFEST,
                    dataset_id=volume.dataset_id,
                    blockdevice_id=volume.blockdevice_id,
                    maximum_size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE,
                ),
            ],
        )

    @capture_logging(
        assertHasMessage,
        INVALID_DEVICE_PATH, {
            u"invalid_value": FilePath(b"/definitely/wrong"),
        },
    )
    def test_attached_with_incorrect_device_path(self, logger):
        """
        If a volume is attached but the ``IBlockDeviceAPI`` returns a path that
        is not a block device, an error is logged and no manifestation
        corresponding to the volume is included in the discovered state.
        """
        self.patch(blockdevice, "_logger", logger)
        self._incorrect_device_path_test(FilePath(b"/definitely/wrong"))

    @capture_logging(
        assertHasMessage,
        INVALID_DEVICE_PATH, {
            u"invalid_value": None,
        },
    )
    def test_attached_with_wrong_device_path_type(self, logger):
        """
        If a volume is attached but the ``IBlockDeviceAPI`` returns a value
        other than a ``FilePath``, an error is logged and no manifestation
        corresponding to the volume is included in the discovered state.
        """
        self.patch(blockdevice, "_logger", logger)
        self._incorrect_device_path_test(None)

    def test_only_remote_device(self):
        """
        If a volume is attached to a remote node, the dataset returned by
        ``BlockDeviceDeployer.discover_state`` is marked as
        ``ATTACHED_ELSEWHERE``.
        """
        dataset_id = uuid4()
        volume = self.api.create_volume(
            dataset_id=dataset_id,
            size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE
        )
        self.api.attach_volume(
            volume.blockdevice_id,
            # This is a hack.  We don't know any other IDs, though.
            # https://clusterhq.atlassian.net/browse/FLOC-1839
            attach_to=u'some.other.host',
        )
        assert_discovered_state(
            self, self.deployer,
            expected_discovered_datasets=[
                DiscoveredDataset(
                    state=DatasetStates.ATTACHED_ELSEWHERE,
                    dataset_id=volume.dataset_id,
                    blockdevice_id=volume.blockdevice_id,
                    maximum_size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE,
                ),
            ],
        )

    def test_unrelated_mounted(self):
        """
        If a volume is attached but an unrelated filesystem is mounted at
        the expected location for that volume, it is recognized as not
        being in ``MOUNTED`` state.
        """
        # XXX This should perhaps be a seperate state so this can be
        # fixed.
        unrelated_device = FilePath(self.mktemp())
        with unrelated_device.open("w") as unrelated_file:
            unrelated_file.truncate(LOOPBACK_MINIMUM_ALLOCATABLE_SIZE)

        volume = self.api.create_volume(
            dataset_id=uuid4(),
            size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE,
        )
        mountpoint = self.deployer.mountroot.child(bytes(volume.dataset_id))
        mountpoint.makedirs()
        self.api.attach_volume(
            volume.blockdevice_id,
            attach_to=self.this_node,
        )

        make_filesystem(unrelated_device, block_device=False)
        mount(unrelated_device, mountpoint)

        device_path = self.api.get_device_path(
            volume.blockdevice_id,
        )

        assert_discovered_state(
            self, self.deployer,
            expected_discovered_datasets=[
                DiscoveredDataset(
                    state=DatasetStates.ATTACHED_NO_FILESYSTEM,
                    dataset_id=volume.dataset_id,
                    blockdevice_id=volume.blockdevice_id,
                    maximum_size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE,
                    device_path=device_path,
                ),
            ],
        )

    def test_attached_no_filesystem(self):
        """
        An attached volume with no filesystem ends up in
        ATTACHED_NO_FILESYSTEM state.
        """
        volume = self.api.create_volume(
            dataset_id=uuid4(),
            size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE,
        )
        self.api.attach_volume(
            volume.blockdevice_id,
            attach_to=self.this_node,
        )
        device_path = self.api.get_device_path(volume.blockdevice_id)
        assert_discovered_state(
            self, self.deployer,
            expected_discovered_datasets=[
                DiscoveredDataset(
                    state=DatasetStates.ATTACHED_NO_FILESYSTEM,
                    dataset_id=volume.dataset_id,
                    blockdevice_id=volume.blockdevice_id,
                    maximum_size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE,
                    device_path=device_path,
                ),
            ],
        )


@implementer(IBlockDeviceAPI)
class UnusableAPI(object):
    """
    A non-implementation of ``IBlockDeviceAPI`` where it is explicitly required
    that the object not be used for anything.
    """


@implementer(ICalculator)
class RecordingCalculator(object):
    """
    An ``ICalculator`` that records the datasets passed to it, and calculates a
    fixed change.
    """
    def __init__(self, expected_changes):
        self.expected_changes = expected_changes

    def calculate_changes_for_datasets(
        self, discovered_datasets, desired_datasets,
    ):
        self.discovered_datasets = discovered_datasets
        self.desired_datasets = desired_datasets
        return self.expected_changes


def make_icalculator_tests(calculator_factory):
    """
    Make a test case to test an ``ICalculator`` implementation.

    :param calculator_factory: Factory to make an ``ICalculator`` provider.
    :type calculator_factory: No argument ``callable``.

    :return: A ``TestCase`` subclass.
    """
    class ICalculatorTests(SynchronousTestCase):
        """
        Tests of an ``ICalculator`` implementation.
        """
        def test_interface(self):
            """
            The ``ICalculator`` implemention actually implements the interface.
            """
            verifyObject(ICalculator, calculator_factory())

        @given(
            discovered_datasets=builds(
                dataset_map_from_iterable,
                lists(DISCOVERED_DATASET_STRATEGY),
            ),
            desired_datasets=builds(
                dataset_map_from_iterable,
                lists(DESIRED_DATASET_STRATEGY),
            ),
        )
        def test_returns_changes(self, discovered_datasets, desired_datasets):
            """
            ``ICalculator.calculate_changes_for_datasets`` returns a
            ``IStateChange``.
            """
            calculator = calculator_factory()
            changes = calculator.calculate_changes_for_datasets(
                discovered_datasets=discovered_datasets,
                desired_datasets=desired_datasets)
            self.assertTrue(IStateChange.providedBy(changes))

    return ICalculatorTests


class BlockDeviceCalculatorInterfaceTests(
    make_icalculator_tests(BlockDeviceCalculator)
):
    """
    Tests for ``BlockDeviceCalculator``'s implementation of ``ICalculator``.
    """


class RecordingCalculatorInterfaceTests(
    make_icalculator_tests(lambda: RecordingCalculator(NoOp()))
):
    """
    Tests for ``RecordingCalculator``'s implementation of ``ICalculator``.
    """


def compare_dataset_state(discovered_dataset, desired_dataset):
    """
    Compare a discovered dataset to a desired dataset to determine if they have
    converged.

    .. note:: This ignores ``maximum_size`` as we don't support resizing yet.

    :return: ``bool`` indicating if the datasets correspond.
    """
    if discovered_dataset is None:
        return (desired_dataset is None
                or desired_dataset.state == DatasetStates.DELETED)
    if desired_dataset is None:
        return discovered_dataset.state == DatasetStates.NON_MANIFEST
    if discovered_dataset.state != desired_dataset.state:
        return False
    if discovered_dataset.state == DatasetStates.MOUNTED:
        return discovered_dataset.mount_point == desired_dataset.mount_point
    elif discovered_dataset.state == DatasetStates.NON_MANIFEST:
        return True
    elif discovered_dataset.state == DatasetStates.DELETED:
        return True
    else:
        raise ValueError("Impossible dataset states: {} {}".format(
            discovered_dataset, desired_dataset,
        ))


def compare_dataset_states(discovered_datasets, desired_datasets):
    """
    Compare discovered and desired state of datasets to determine if they have
    converged.

    .. note:: This ignores ``maximum_size`` as we don't support resizing yet.

    :return: ``bool`` indicating if the datasets correspond.
    """
    for dataset_id in set(discovered_datasets) | set(desired_datasets):
        desired_dataset = desired_datasets.get(dataset_id)
        discovered_dataset = discovered_datasets.get(dataset_id)
        if not compare_dataset_state(
            discovered_dataset=discovered_dataset,
            desired_dataset=desired_dataset,
        ):
            return False
    return True


@attributes(["iteration_count"])
class DidNotConverge(Exception):
    """
    Raised if running convergence with an ``ICalculator`` does not converge
    in the specified number of iterations.

    :ivar iteration_count: The count of iterations before this was raised.
    """


class _WriteVerifyingExternalClient(object):
    """
    Representation of an external client of the Flocker API. This client can be
    used to try to write to paths on the system and verify that the writes are
    persisted to the underlying blockdevice.

    :ivar _known_mountpoints: Known mountpoints of the dataset. Once flocker
        has returned a path to an external agent, there is no promising how
        long that agent might cache that information before it tries to write
        to that location. This agent keeps track of all mountpoints it has ever
        seen and tries to write to all of them.
    :ivar _device_path: The device path of the blockdevice that backs the
        dataset. This is used to verify that writes are persisted to the
        underlying blockdevice.
    :ivar _dataset_id: The dataset_id of the dataset under test.
    :ivar _node_uuid: The node_uuid of the node that is being tested.
    :ivar _testing_mountroot: A mountroot to construct moutpoints under.
    :ivar _blockdevice_manager: An ``IBlockDeviceManager`` provider that can be
        used to mount block devices.
    """

    def __init__(self, dataset_id, node_uuid, mountroot, blockdevice_manager):
        self._known_mountpoints = set()
        self._device_path = None
        self._dataset_id = dataset_id
        self._node_uuid = node_uuid
        self._testing_mountroot = mountroot
        self._blockdevice_manager = blockdevice_manager

    def _has_file_named(self, filename):
        """
        Returns whether the blockdevice at self._device_path has a file with
        the given name.
        """
        test_mountpoint = self._testing_mountroot.child(str(uuid4()))
        test_mountpoint.makedirs()
        self._blockdevice_manager.mount(self._device_path, test_mountpoint)
        result = test_mountpoint.child(filename).exists()
        self._blockdevice_manager.unmount(self._device_path)
        test_mountpoint.remove()
        return result

    def invariant(self, case, current_cluster_state):
        """
        An invariant that should always hold. Specifically, after the path
        to a dataset is known by the cluster then writes to that path
        should either succeed and be persisted to the underlying block
        device, or the write should fail.

        :param case: A ``TestCase`` to use for making assertions.
        :param current_cluster_state: A callable that returns the current state
            of the cluster.

        :returns: False if none of the known paths of the dataset can be
            written to.
        """
        write_success = []

        # First poll the cluster state to see if there is a new mountpoint that
        # we should try to use to attempt to write to the dataset.
        [node] = list(n for n in current_cluster_state().nodes
                      if n.uuid == self._node_uuid)
        paths = node.paths or {}
        path = paths.get(unicode(self._dataset_id))
        if path:
            self._known_mountpoints.add(path)
        devices = node.devices or {}
        device = devices.get(self._dataset_id)
        if device:
            self._device_path = device

        for path in self._known_mountpoints:
            device = self._device_path
            filename = str(uuid4())
            try:
                path.child(filename).touch()
            except OSError:
                # If we failed to write, that is okay in many scenarios. At
                # least the failing write won't lead to the end user
                # thinking that they have an actually persisted data. Note
                # the failure, but don't immediately fail the test.
                write_success.append(False)
            else:
                write_success.append(True)
                case.assertTrue(
                    self._has_file_named(filename),
                    "Successfully wrote to a path gotten from flocker, "
                    "but the write was not persisted to the backing block "
                    "device.")
        return any(write_success)


class BlockDeviceCalculatorTests(SynchronousTestCase):
    """
    Tests for ``BlockDeviceCalculator``.
    """
    def setUp(self):
        self._deployer = None
        self._cluster_state = DeploymentState(nodes=[self._empty_node_state()])

    @property
    def deployer(self):
        """
        Lazily created ``BlockDeviceDeployer``. Tests that want to initialize
        their own can do so by initializing self._deployer.
        """
        if self._deployer is None:
            self._deployer = create_blockdevicedeployer(self)
        return self._deployer

    def _empty_node_state(self):
        """
        Returns an empty node state for the node the deployer is created on.
        """
        return NodeState(
            uuid=self.deployer.node_uuid,
            hostname=self.deployer.hostname,
            applications=[],
        )

    def teardown_example(self, token):
        """
        Cleanup after running a hypothesis example.
        """
        detach_destroy_volumes(self.deployer.block_device_api)

    def current_local_state(self):
        """
        Return the current ``BlockDeviceDeployerLocalState`` from the deployer.
        """
        local_state = self.successResultOf(self.deployer.discover_state(
            self._empty_node_state()
        ))

        for change in local_state.shared_state_changes():
            self._cluster_state = change.update_cluster_state(
                self._cluster_state)
        return local_state

    def current_datasets(self):
        """
        Return the current state of datasets from the deployer.
        """
        return self.current_local_state().datasets

    def current_cluster_state(self):
        """
        Return the current state of the cluster.
        """
        return self._cluster_state

    def run_convergence_step(self, desired_datasets):
        """
        Run one step of the calculator.

        :param desired_datasets: The dataset state to converge to.
        :type desired_datasets: Mapping from ``UUID`` to ``DesiredDataset``.
        """
        local_datasets = self.current_datasets()
        changes = self.deployer.calculator.calculate_changes_for_datasets(
            discovered_datasets=local_datasets,
            desired_datasets=desired_datasets,
        )
        note("Running changes: {changes}".format(changes=changes))
        self.successResultOf(run_state_change(changes, self.deployer))

    def run_to_convergence(self, desired_datasets, max_iterations=6):
        """
        Run the calculator until it converges on the desired state.

        :param desired_datasets: The dataset state to converge to.
        :type desired_datasets: Mapping from ``UUID`` to ``DesiredDataset``.
        :param int max_iterations: The maximum number of steps to iterate.
        """
        for i in range(max_iterations):
            self.run_convergence_step(
                dataset_map_from_iterable(desired_datasets))
            note(self.current_datasets())
            if compare_dataset_states(
                self.current_datasets(),
                dataset_map_from_iterable(desired_datasets),
            ):
                break
        else:
            raise DidNotConverge(iteration_count=max_iterations)

    @given(
        initial_dataset=DESIRED_DATASET_STRATEGY,
        next_dataset=DESIRED_DATASET_STRATEGY,
    )
    def test_simple_transitions(self, initial_dataset, next_dataset):
        """
        Given an initial empty state, ``BlockDeviceCalculator`` will converge
        to any ``DesiredDataset``, followed by any other state of the same
        dataset.
        """
        dataset_id = initial_dataset.dataset_id

        # Set the mountpoint to a real mountpoint in desired dataset states
        # that have a mount point attribute.
        mount_point = self.deployer._mountpath_for_dataset_id(
            unicode(dataset_id))
        if hasattr(initial_dataset, 'mount_point'):
            initial_dataset = initial_dataset.set(mount_point=mount_point)
        if hasattr(next_dataset, 'mount_point'):
            next_dataset = next_dataset.set(mount_point=mount_point)

        # Merge fields from initial_dataset into next_dataset (such as
        # dataset_id) so that we are changing the desired state of the same
        # dataset.
        next_dataset = merge_tagged_unions(DesiredDataset,
                                           initial_dataset,
                                           next_dataset)

        # Converge to the initial state.
        try:
            self.run_to_convergence([initial_dataset])
        except DidNotConverge as e:
            self.fail(
                "Did not converge to initial state after %d iterations." %
                e.iteration_count)

        # Converge from the initial state to the next state.
        try:
            self.run_to_convergence([next_dataset])
        except DidNotConverge as e:
            self.fail("Did not converge to next state after %d iterations." %
                      e.iteration_count)

    @given(
        initial_dataset=DESIRED_DATASET_STRATEGY,
        next_dataset=DESIRED_DATASET_STRATEGY,
    )
    def test_docker_protection(self, initial_dataset, next_dataset):
        """
        Given an initial empty state, ``BlockDeviceCalculator`` will converge
        to any ``DesiredDataset``, followed by any other state of the same
        dataset. During that time, it will never be the case that a
        successfully write to a mount path that has been sent to the control
        agent will not be persisted to the backing volume.

        This would represent an agent like docker attempting to use a path
        before or after flocker was ready for it to use the path.
        """
        dataset_id = initial_dataset.dataset_id

        evaluate_function = None

        def nullable_callback():
            if evaluate_function:
                evaluate_function()

        actual_blockdevice_manager = BlockDeviceManager()
        proxy_blockdevice_manager = create_callback_blockdevice_manager_proxy(
            actual_blockdevice_manager, nullable_callback)

        self._deployer = create_blockdevicedeployer(
            self, block_device_manager=proxy_blockdevice_manager)

        external_agent = _WriteVerifyingExternalClient(
            dataset_id,
            self.deployer.node_uuid,
            mountroot_for_test(self),
            actual_blockdevice_manager)

        evaluate_function = partial(external_agent.invariant, self,
                                    self.current_cluster_state)
        print evaluate_function

        # Set the mountpoint to a real mountpoint in desired dataset states
        # that have a mount point attribute.
        mount_point = self.deployer._mountpath_for_dataset_id(
            unicode(dataset_id))
        if hasattr(initial_dataset, 'mount_point'):
            initial_dataset = initial_dataset.set(mount_point=mount_point)
        if hasattr(next_dataset, 'mount_point'):
            next_dataset = next_dataset.set(mount_point=mount_point)

        # Merge fields from initial_dataset into next_dataset (such as
        # dataset_id) so that we are changing the desired state of the same
        # dataset.
        next_dataset = merge_tagged_unions(DesiredDataset,
                                           initial_dataset,
                                           next_dataset)

        # Converge to the initial state.
        try:
            self.run_to_convergence([initial_dataset])
        except DidNotConverge as e:
            self.fail(
                "Did not converge to initial state after %d iterations." %
                e.iteration_count)

        # Converge from the initial state to the next state.
        try:
            self.run_to_convergence([next_dataset])
        except DidNotConverge as e:
            self.fail("Did not converge to next state after %d iterations." %
                      e.iteration_count)

    @given(
        desired_state=sampled_from([
            DatasetStates.MOUNTED, DatasetStates.NON_MANIFEST,
            DatasetStates.DELETED,
        ]),
        discovered_state=sampled_from(
            DiscoveredDataset.__invariant__.attributes_for_tag.keys()
            + [DatasetStates.NON_EXISTENT]
        )
    )
    def test_all_transitions(self, desired_state, discovered_state):
        """
        Transitions are defined from all possible desired states towards
        all possible discovered states.
        """
        assume(desired_state != discovered_state)
        verifyObject(
            IDatasetStateChangeFactory,
            DATASET_TRANSITIONS[desired_state][discovered_state],
        )


def assert_desired_datasets(
    case,
    deployer,
    desired_manifestations=(),
    local_datasets=(),
    local_applications=(),
    additional_node_config=set(),
    expected_datasets=(),
    leases=Leases(),
):
    """
    Assert that ``calculate_changes`` calculates the given desired datasets
    invoked with the given state and configuration.

    :param TestCase test_case: The ``TestCase`` which is being run.
    :param BlockDeviceDeployer deployer: The deployer that will be asked to
        calculate the desired datasets.
    :param desired_manifestations: Manifestations to include in the local nodes
        configuration.
    :type desired_manifestations: iterable of ``Manifestations``
    :param local_datasets: Datasets to include in the local node's state.
    :type local_datasets: iterable of ``DiscoveredDataset``s
    :param local_applications: Location to include in the local node's state.
    :type local_applications: iterable of ``Application``s
    :param additonal_node_config: Additional nodes to include in the cluster
        configration.
    :type additional_node_config: ``set`` of ``Node``s
    :param Leases leases: Leases to include in the cluster configration.
    """
    calculator = RecordingCalculator(NoOp())
    deployer = deployer.set(calculator=calculator)
    cluster_configuration = Deployment(
        nodes={
            Node(
                uuid=deployer.node_uuid,
                hostname=deployer.hostname,
                manifestations={
                    manifestation.dataset.dataset_id: manifestation
                    for manifestation in desired_manifestations
                },
            ),
        } | additional_node_config,
        leases=leases,
    )

    local_state = BlockDeviceDeployerLocalState(
        node_uuid=deployer.node_uuid,
        hostname=deployer.hostname,
        datasets={dataset.dataset_id: dataset
                  for dataset in local_datasets},
    )
    node_state, nonmanifest_datasets = local_state.shared_state_changes()
    cluster_state = DeploymentState(
        nodes={node_state.set(applications=local_applications)},
        nonmanifest_datasets=nonmanifest_datasets.datasets,
    )

    deployer.calculate_changes(
        configuration=cluster_configuration,
        cluster_state=cluster_state,
        local_state=local_state,
    )
    case.assertEqual(
        {dataset.dataset_id: dataset
         for dataset in expected_datasets},
        calculator.desired_datasets,
    )


class CalculateDesiredStateTests(SynchronousTestCase):
    """
    Tests for ``BlockDeviceDeployer._calculate_desired_state``.
    """
    def setUp(self):
        self.hostname = ScenarioMixin.NODE
        self.node_uuid = ScenarioMixin.NODE_UUID
        self.api = UnusableAPI()
        self.deployer = BlockDeviceDeployer(
            node_uuid=self.node_uuid,
            hostname=self.hostname,
            block_device_api=self.api,
            mountroot=FilePath('/flocker'),
        )

    def test_no_manifestations(self):
        """
        If there are no Manifestations on this node, then
        there are no desired datasets calculated.
        """
        assert_desired_datasets(
            self, self.deployer,
            desired_manifestations=[],
            expected_datasets=[],
        )

    def test_manifestation(self):
        """
        If there is a manifesation configured on this node, then the
        corresponding desired dataset has a state of ``MOUNTED``.
        """
        assert_desired_datasets(
            self, self.deployer,
            desired_manifestations=[ScenarioMixin.MANIFESTATION],
            expected_datasets=[ScenarioMixin.MOUNTED_DESIRED_DATASET],
        )

    def test_manifestation_metadata(self):
        """
        If there is a manifesation configured with metadata on this node, then
        the corresponding desired dataset has that metadata.
        """
        assert_desired_datasets(
            self, self.deployer,
            desired_manifestations=[ScenarioMixin.MANIFESTATION.transform(
                ['dataset', 'metadata'], ScenarioMixin.METADATA,
            )],
            expected_datasets=[ScenarioMixin.MOUNTED_DESIRED_DATASET.transform(
                ['metadata'], ScenarioMixin.METADATA,
            )],
        )

    def test_manifestation_default_size(self):
        """
        If there is a manifesation configured on this node without a size, then
        the corresponding desired dataset has a size fixed to the
        minimum allowed Rackspace volume size.

        XXX: Make the default size configurable.  FLOC-2679
        """
        expected_size = int(RACKSPACE_MINIMUM_VOLUME_SIZE.bytes)
        assert_desired_datasets(
            self, self.deployer,
            desired_manifestations=[
                ScenarioMixin.MANIFESTATION.transform(
                    ["dataset", "maximum_size"], lambda _: None,
                ),
            ],
            expected_datasets=[
                ScenarioMixin.MOUNTED_DESIRED_DATASET.transform(
                    ['maximum_size'], expected_size,
                ),
            ],
        )

    def test_deleted_dataset(self):
        """
        If there is a dataset that is configured as deleted on this node, the
        corresponding dataset has a desired state of ``DELETED``.
        """
        assert_desired_datasets(
            self, self.deployer,
            desired_manifestations=[
                ScenarioMixin.MANIFESTATION.transform(
                    ["dataset", "deleted"], True,
                    ['dataset', 'metadata'], ScenarioMixin.METADATA,
                ),
            ],
            local_datasets=[],
            expected_datasets=[
                DesiredDataset(
                    state=DatasetStates.DELETED,
                    dataset_id=ScenarioMixin.DATASET_ID,
                    metadata=ScenarioMixin.METADATA,
                ),
            ],
        )

    @given(
        expected_size=integers(min_value=0),
    )
    def test_leased_mounted_manifestation(self, expected_size):
        """
        If there is a lease for a mounted dataset present on node, there is a
        corresponding desired dataset that has a state of ``MOUNTED`` even if
        the configuration of the node doesn't mention the dataset.
        """
        assert_desired_datasets(
            self, self.deployer,
            desired_manifestations=[],
            local_datasets=[
                ScenarioMixin.MOUNTED_DISCOVERED_DATASET.transform(
                    ['maximum_size'], expected_size,
                ),
            ],
            expected_datasets=[
                ScenarioMixin.MOUNTED_DESIRED_DATASET.transform(
                    ['maximum_size'], expected_size,
                ),
            ],
            leases=Leases().acquire(
                now=datetime.now(tz=UTC),
                dataset_id=ScenarioMixin.DATASET_ID,
                node_id=self.deployer.node_uuid,
            )
        )

    @given(
        local_dataset=DISCOVERED_DATASET_STRATEGY.filter(
            lambda dataset: dataset.state != DatasetStates.MOUNTED,
        ),
    )
    def test_leased_not_mounted(self, local_dataset):
        """
        If there is a lease for a dataset that isn't mounted on the node and
        the dataset isn't requested in the configuration of the node, there is
        not a corresponding desired dataset.
        """
        assert_desired_datasets(
            self, self.deployer,
            desired_manifestations=[],
            local_datasets=[local_dataset],
            expected_datasets=[],
            leases=Leases().acquire(
                now=datetime.now(tz=UTC),
                dataset_id=local_dataset.dataset_id,
                node_id=self.deployer.node_uuid,
            )
        )

    def test_lease_elsewhere(self):
        """
        If there is a lease for a dataset on another node, there isn't a
        corresponding desired dataset.
        """
        assert_desired_datasets(
            self, self.deployer,
            local_datasets=[
                ScenarioMixin.MOUNTED_DISCOVERED_DATASET,
            ],
            expected_datasets=[],
            leases=Leases().acquire(
                now=datetime.now(tz=UTC),
                dataset_id=ScenarioMixin.DATASET_ID,
                node_id=uuid4(),
            )
        )

    def test_application_mounted_manifestation(self):
        """
        If there is an application with attached volume, there is a
        corresponding desired dataset that has a state of ``MOUNTED``.
        """
        assert_desired_datasets(
            self, self.deployer,
            desired_manifestations=[],
            local_datasets=[
                ScenarioMixin.MOUNTED_DISCOVERED_DATASET,
            ],
            local_applications=[
                Application(
                    name=u"myapplication",
                    image=DockerImage.from_string(u"image"),
                    volume=AttachedVolume(
                        manifestation=ScenarioMixin.MANIFESTATION,
                        mountpoint=FilePath(b"/data")
                    ),
                ),
            ],
            expected_datasets=[
                ScenarioMixin.MOUNTED_DESIRED_DATASET,
            ],
        )

    @given(
        expected_size=integers(min_value=0),
    )
    def test_leased_manifestation(self, expected_size):
        """
        If there is a manifesation on this node and lease for the corresponding
        volume for this node, then the corresponding desired dataset has a
        state of ``MOUNTED`` and the associated size corresponds to the
        discovered dataset.
        """
        assert_desired_datasets(
            self, self.deployer,
            desired_manifestations=[ScenarioMixin.MANIFESTATION],
            local_datasets=[
                ScenarioMixin.MOUNTED_DISCOVERED_DATASET.transform(
                    ['maximum_size'], expected_size,
                ),
            ],
            expected_datasets=[
                ScenarioMixin.MOUNTED_DESIRED_DATASET.transform(
                    ['maximum_size'], expected_size,
                ),
            ],
            leases=Leases().acquire(
                now=datetime.now(tz=UTC),
                dataset_id=ScenarioMixin.DATASET_ID,
                node_id=self.deployer.node_uuid,
            )
        )

    def test_deleted_leased_manifestation(self):
        """
        If there is a manfestation on this node that is configured as deleted
        and there is a lease on the volume for this node, the corresponding
        desired dataset has a state of ``MOUNTED``.
        """
        assert_desired_datasets(
            self, self.deployer,
            desired_manifestations=[
                ScenarioMixin.MANIFESTATION.transform(
                    ["dataset"], lambda d: d.set(deleted=True)
                ),
            ],
            local_datasets=[
                ScenarioMixin.MOUNTED_DISCOVERED_DATASET,
            ],
            expected_datasets=[
                ScenarioMixin.MOUNTED_DESIRED_DATASET,
            ],
            leases=Leases().acquire(
                now=datetime.now(tz=UTC),
                dataset_id=ScenarioMixin.DATASET_ID,
                node_id=self.deployer.node_uuid,
            )
        )


def assert_calculated_changes(
        case, node_state, node_config, nonmanifest_datasets, expected_changes,
        additional_node_states=frozenset(), leases=Leases(),
        discovered_datasets=None,
):
    """
    Assert that ``BlockDeviceDeployer`` calculates certain changes in a certain
    circumstance.

    :param discovered_datasets: Collection of ``DiscoveredDataset`` to
        expose as local state.
    :see: ``assert_calculated_changes_for_deployer``.
    """
    api = UnusableAPI()

    deployer = BlockDeviceDeployer(
        node_uuid=node_state.uuid,
        hostname=node_state.hostname,
        block_device_api=api,
    )

    cluster_state = compute_cluster_state(node_state, additional_node_states,
                                          nonmanifest_datasets)

    if discovered_datasets is None:
        local_state = local_state_from_shared_state(
            node_state=node_state,
            nonmanifest_datasets=cluster_state.nonmanifest_datasets,
        )
    else:
        local_state = BlockDeviceDeployerLocalState(
            node_uuid=node_state.uuid,
            hostname=node_state.hostname,
            datasets=dataset_map_from_iterable(discovered_datasets),
        )
        case.assertEqual(
            local_state.shared_state_changes(),
            (node_state.set("applications", None), NonManifestDatasets(
                datasets=cluster_state.nonmanifest_datasets)),
            "Inconsistent test data."
        )

    return assert_calculated_changes_for_deployer(
        case, deployer, node_state, node_config,
        nonmanifest_datasets, additional_node_states, set(),
        expected_changes, local_state, leases=leases,
    )


def _create_blockdevice_id_for_test(dataset_id):
    """
    Generates a blockdevice_id from a dataset_id for tests that do not use an
    ``IBlockDeviceAPI``.

    :param dataset_id: A unicode or uuid dataset_id to generate the
        blockdevice_id for.
    """
    return "blockdevice-" + unicode(dataset_id)


class ScenarioMixin(object):
    """
    A mixin for tests which defines some basic Flocker cluster state.
    """
    DATASET_ID = uuid4()
    BLOCKDEVICE_ID = _create_blockdevice_id_for_test(DATASET_ID)
    NODE = u"192.0.2.1"
    NODE_UUID = uuid4()

    METADATA = {u"I'm so meta": u"even this acronym"}

    MANIFESTATION = Manifestation(
        dataset=Dataset(
            dataset_id=unicode(DATASET_ID),
            maximum_size=int(REALISTIC_BLOCKDEVICE_SIZE.to_Byte()),
        ),
        primary=True,
    )

    # The state of a single node which has a single primary manifestation for a
    # dataset.  Common starting point for several of the test scenarios.
    ONE_DATASET_STATE = NodeState(
        hostname=NODE,
        uuid=NODE_UUID,
        manifestations={
            unicode(DATASET_ID): MANIFESTATION,
        },
        paths={
            unicode(DATASET_ID):
            FilePath(b"/flocker/").child(bytes(DATASET_ID)),
        },
        devices={
            DATASET_ID: FilePath(b"/dev/sda"),
        },
        applications=[],
    )

    MOUNT_ROOT = FilePath('/flocker')
    MOUNTED_DISCOVERED_DATASET = DiscoveredDataset(
        dataset_id=DATASET_ID,
        blockdevice_id=BLOCKDEVICE_ID,
        state=DatasetStates.MOUNTED,
        maximum_size=int(REALISTIC_BLOCKDEVICE_SIZE.bytes),
        device_path=FilePath('/dev/xvdf'),
        mount_point=MOUNT_ROOT,
    )
    MOUNTED_DESIRED_DATASET = DesiredDataset(
        state=DatasetStates.MOUNTED,
        dataset_id=DATASET_ID,
        maximum_size=int(REALISTIC_BLOCKDEVICE_SIZE.bytes),
        mount_point=MOUNT_ROOT.child(
            unicode(DATASET_ID)
        ),
    )


def add_application_with_volume(node_state):
    """
    Add a matching application that has the current dataset attached as a
    volume.

    :param NodeState node_state: Has dataset with ID ``DATASET_ID``.

    :return NodeState: With ``Application`` added.
    """
    manifestation = list(node_state.manifestations.values())[0]
    return node_state.set(
        "applications", {Application(
            name=u"myapplication",
            image=DockerImage.from_string(u"image"),
            volume=AttachedVolume(manifestation=manifestation,
                                  mountpoint=FilePath(b"/data")))})


def create_test_blockdevice_volume_for_dataset_id(dataset_id,
                                                  attached_to=None):
    """
    Create a fake ``BlockDeviceVolume`` for the given ``dataset_id``,
    attached to the given node.

    :param dataset_id: A unicode or uuid dataset_id to generate the
        blockdevice_id for.
    :param unicode attached_to: The compute_instance_id this volume should be
        attached to.
    """

    return BlockDeviceVolume(
        blockdevice_id=_create_blockdevice_id_for_test(dataset_id),
        size=int(REALISTIC_BLOCKDEVICE_SIZE.to_Byte()),
        attached_to=attached_to,
        dataset_id=UUID(dataset_id))


@implementer(ILocalState)
def local_state_from_shared_state(
    node_state,
    nonmanifest_datasets,
):
    """
    Convert the state as reported by
    ``BlockDeviceDeployerLocalState.shared_state_changes`` to a
    ``BlockDeviceDeployerLocalState`` instance.

    This exists so that tests that provide the former can be used
    with an implementation that expects the former.

    .. warning:: This function is a terrible idea and should be thrown out ASAP
    to be replaced by the real thing.
    """
    datasets = {}
    for dataset_id, dataset in nonmanifest_datasets.items():
        dataset_id = UUID(dataset_id)
        if dataset_id in node_state.devices:
            datasets[dataset_id] = DiscoveredDataset(
                state=DatasetStates.ATTACHED,
                dataset_id=dataset_id,
                maximum_size=dataset.maximum_size or 0,
                device_path=node_state.devices[dataset_id],
                blockdevice_id=_create_blockdevice_id_for_test(dataset_id),
            )
        else:
            datasets[dataset_id] = DiscoveredDataset(
                state=DatasetStates.NON_MANIFEST,
                dataset_id=dataset_id,
                maximum_size=dataset.maximum_size or 0,
                blockdevice_id=_create_blockdevice_id_for_test(dataset_id),
            )

    if node_state.manifestations is not None:
        for dataset_id, manifestation in node_state.manifestations.items():
            dataset_id = UUID(dataset_id)
            datasets[dataset_id] = DiscoveredDataset(
                state=DatasetStates.MOUNTED,
                dataset_id=dataset_id,
                maximum_size=manifestation.dataset.maximum_size or 0,
                device_path=node_state.devices[dataset_id],
                blockdevice_id=_create_blockdevice_id_for_test(dataset_id),
                mount_point=node_state.paths[unicode(dataset_id)],
            )

    return BlockDeviceDeployerLocalState(
        hostname=node_state.hostname,
        node_uuid=node_state.uuid,
        datasets=datasets,
    )


class LocalStateFromSharedStateTests(SynchronousTestCase):
    """
    Tests for ``local_state_from_shared_state``.
    """
    @given(
        local_state=builds(
            BlockDeviceDeployerLocalState,
            node_uuid=uuids(),
            hostname=text(),
            datasets=lists(
                DISCOVERED_DATASET_STRATEGY,
            ).map(dataset_map_from_iterable),
        )
    )
    def test_round_trip(self, local_state):
        """
        Calling ``local_state_from_shared_state`` followed by ``
        ``BlockDeviceDeployerLocalState.shared_state_changes`` on
        the state changes of a ``BlockDeviceDeployerLocalState`` is
        idempotent.
        """
        node_state, nonmanifest_datasets = local_state.shared_state_changes()
        fake_local_state = local_state_from_shared_state(
            node_state=node_state,
            nonmanifest_datasets=nonmanifest_datasets.datasets,
        )
        self.assertEqual(local_state.shared_state_changes(),
                         fake_local_state.shared_state_changes())


class BlockDeviceDeployerAlreadyConvergedCalculateChangesTests(
        SynchronousTestCase, ScenarioMixin
):
    """
    Tests for the cases of ``BlockDeviceDeployer.calculate_changes`` where no
    changes are necessary because the local state already matches the desired
    configuration.
    """
    def test_no_changes(self):
        """
        ``BlockDeviceDeployer.calculate_changes`` calculates no changes when
        the local state is already converged with the desired configuration.
        """
        local_state = self.ONE_DATASET_STATE
        local_config = to_node(local_state)

        assert_calculated_changes(
            self, local_state, local_config, set(),
            NoOp(),
        )

    def test_deleted_ignored(self):
        """
        Deleted datasets for which no corresponding volumes exist do not result
        in any convergence operations.
        """
        local_state = self.ONE_DATASET_STATE.transform(
            # Remove the dataset.  This reflects its deletedness.
            ["manifestations", unicode(self.DATASET_ID)], discard,
            # Remove its device too.
            ["devices", self.DATASET_ID], discard,
            # Remove its mountpoint too.
            ["paths", unicode(self.DATASET_ID)], discard,
        )

        local_config = to_node(self.ONE_DATASET_STATE).transform(
            ["manifestations", unicode(self.DATASET_ID), "dataset"],
            lambda d: d.set(
                # Mark it as deleted in the configuration.
                deleted=True,
                # Change a bunch of other things too.  They shouldn't matter.
                maximum_size=d.maximum_size * 2,
                metadata={u"foo": u"bar"},
            )
        )

        assert_calculated_changes(
            self, local_state, local_config,
            nonmanifest_datasets={},
            expected_changes=in_parallel(changes=[]),
        )


class BlockDeviceDeployerIgnorantCalculateChangesTests(
        SynchronousTestCase, ScenarioMixin
):
    """
    Tests for the cases of ``BlockDeviceDeployer.calculate_changes`` where no
    changes can be calculated because application state is unknown.
    """
    def test_unknown_applications(self):
        """
        If applications are unknown, no changes are calculated.
        """
        # We're ignorant about application state:
        local_state = NodeState(
            hostname=self.NODE, uuid=self.NODE_UUID, applications=None)

        # We want to create a dataset:
        local_config = to_node(self.ONE_DATASET_STATE)

        assert_calculated_changes(self, local_state, local_config, set(),
                                  in_parallel(changes=[]))

    def test_another_node_ignorant(self):
        """
        If a different node is ignorant about its state, it is still possible
        to calculate state for the current node.
        """
        local_state = self.ONE_DATASET_STATE
        local_config = to_node(local_state).transform(
            ["manifestations", unicode(self.DATASET_ID), "dataset", "deleted"],
            True
        )
        assert_calculated_changes(
            self, local_state, local_config, set(),
            in_parallel(changes=[
                UnmountBlockDevice(dataset_id=self.DATASET_ID,
                                   blockdevice_id=self.BLOCKDEVICE_ID)
            ]),
            # Another node which is ignorant about its state:
            set([NodeState(hostname=u"1.2.3.4", uuid=uuid4())])
        )


class BlockDeviceDeployerDestructionCalculateChangesTests(
        SynchronousTestCase, ScenarioMixin
):
    """
    Tests for ``BlockDeviceDeployer.calculate_changes`` in the cases relating
    to dataset destruction.
    """
    def test_deleted_dataset_volume_mounted(self):
        """
        If the configuration indicates a dataset with a primary manifestation
        on the node has been deleted and the volume associated with that
        dataset is mounted, ``BlockDeviceDeployer.calculate_changes`` returns
        a ``UnmountBlockDevice`` state change operation.
        """
        local_state = self.ONE_DATASET_STATE
        local_config = to_node(local_state).transform(
            ["manifestations", unicode(self.DATASET_ID), "dataset", "deleted"],
            True
        )
        assert_calculated_changes(
            self, local_state, local_config, set(),
            in_parallel(changes=[
                UnmountBlockDevice(dataset_id=self.DATASET_ID,
                                   blockdevice_id=self.BLOCKDEVICE_ID)
            ]),
            discovered_datasets=[
                DiscoveredDataset(
                    state=DatasetStates.MOUNTED,
                    dataset_id=self.DATASET_ID,
                    blockdevice_id=self.BLOCKDEVICE_ID,
                    maximum_size=int(REALISTIC_BLOCKDEVICE_SIZE.to_Byte()),
                    device_path=FilePath(b"/dev/sda"),
                    mount_point=FilePath(b"/flocker").child(
                        bytes(self.DATASET_ID),
                    ),
                ),
            ],
        )

    def test_deleted_dataset_volume_detached(self):
        """
        If the configuration indicates a dataset with a primary manifestation
        on the node has been deleted and the volume associated with that
        dataset still exists but is not attached,
        ``BlockDeviceDeployer.calculate_changes`` returns a
        ``DestroyVolume`` state change operation.
        """
        local_state = self.ONE_DATASET_STATE.transform(
            ["manifestations", unicode(self.DATASET_ID)], discard,
            ["paths"], {},
            ["devices"], {},
        )
        local_config = to_node(self.ONE_DATASET_STATE).transform(
            ["manifestations", unicode(self.DATASET_ID), "dataset", "deleted"],
            True
        )
        assert_calculated_changes(
            self, local_state, local_config,
            nonmanifest_datasets=[
                self.MANIFESTATION.dataset,
            ],
            expected_changes=in_parallel(changes=[
                DestroyVolume(blockdevice_id=self.BLOCKDEVICE_ID)
            ]),
            discovered_datasets=[
                DiscoveredDataset(
                    state=DatasetStates.NON_MANIFEST,
                    dataset_id=self.DATASET_ID,
                    blockdevice_id=self.BLOCKDEVICE_ID,
                    maximum_size=int(REALISTIC_BLOCKDEVICE_SIZE.to_Byte()),
                ),
            ],
        )

    def test_deleted_dataset_belongs_to_other_node(self):
        """
        If a dataset with a primary manifestation on one node is marked as
        deleted in the configuration, the ``BlockDeviceDeployer`` for a
        different node does not return a ``DestroyVolume`` from its
        ``calculate_necessary_state_changes`` for that dataset.
        """
        other_node = u"192.0.2.2"
        node_state = self.ONE_DATASET_STATE
        cluster_state = DeploymentState(
            nodes={node_state}
        )

        node_config = to_node(node_state).transform(
            ["manifestations", unicode(self.DATASET_ID), "dataset", "deleted"],
            True
        )
        cluster_configuration = Deployment(
            nodes={node_config}
        )

        api = loopbackblockdeviceapi_for_test(self)
        volume = api.create_volume(
            dataset_id=self.DATASET_ID, size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE
        )
        api.attach_volume(volume.blockdevice_id, self.NODE)

        deployer = BlockDeviceDeployer(
            # This deployer is responsible for *other_node*, not node.
            hostname=other_node,
            node_uuid=uuid4(),
            block_device_api=api,
        )

        local_state = local_state_from_shared_state(
            node_state=node_state,
            nonmanifest_datasets={},
        )
        changes = deployer.calculate_changes(
            cluster_configuration, cluster_state, local_state)

        self.assertEqual(
            in_parallel(changes=[]),
            changes
        )

    def test_no_delete_if_in_use(self):
        """
        If a dataset has been marked as deleted *and* it is in use by an
        application, no changes are made.
        """
        # Application using a dataset:
        local_state = add_application_with_volume(self.ONE_DATASET_STATE)

        # Dataset is deleted:
        local_config = to_node(self.ONE_DATASET_STATE).transform(
            ["manifestations", unicode(self.DATASET_ID), "dataset", "deleted"],
            True)
        local_config = add_application_with_volume(local_config)

        assert_calculated_changes(
            self, local_state, local_config, set(),
            in_parallel(changes=[]),
        )

    def test_no_delete_if_leased(self):
        """
        If a dataset has been marked as deleted *and* it is leased, no changes
        are made.
        """
        # We have a dataset with a lease:
        local_state = self.ONE_DATASET_STATE
        leases = Leases().acquire(datetime.now(tz=UTC), self.DATASET_ID,
                                  self.ONE_DATASET_STATE.uuid)

        # Dataset is deleted:
        local_config = to_node(self.ONE_DATASET_STATE).transform(
            ["manifestations", unicode(self.DATASET_ID), "dataset", "deleted"],
            True)
        local_config = add_application_with_volume(local_config)

        assert_calculated_changes(
            self, local_state, local_config, set(),
            in_parallel(changes=[]), leases=leases,
        )

    def test_deleted_dataset_volume_unmounted(self):
        """
        If the configuration indicates a dataset with a primary manifestation
        on the node has been deleted and the volume associated with that
        dataset is mounted, ``BlockDeviceDeployer.calculate_changes`` returns a
        ``UnmountBlockDevice`` state change operation.
        """
        local_state = self.ONE_DATASET_STATE
        local_config = to_node(local_state).transform(
            ["manifestations", unicode(self.DATASET_ID), "dataset", "deleted"],
            True
        )
        # Remove the manifestation and its mount path.
        local_state = local_state.transform(
            ['manifestations', unicode(self.DATASET_ID)],
            discard
        )
        local_state = local_state.transform(
            ['paths', unicode(self.DATASET_ID)],
            discard
        )
        # Local state shows that there is a device for the (now) non-manifest
        # dataset. i.e it is attached.
        self.assertEqual([self.DATASET_ID], local_state.devices.keys())
        assert_calculated_changes(
            case=self,
            node_state=local_state,
            node_config=local_config,
            # The unmounted dataset has been added back to the non-manifest
            # datasets by discover_state.
            nonmanifest_datasets=[
                self.MANIFESTATION.dataset
            ],
            expected_changes=in_parallel(
                changes=[
                    DetachVolume(
                        dataset_id=self.DATASET_ID,
                        blockdevice_id=self.BLOCKDEVICE_ID,
                    )
                ]
            ),
            discovered_datasets=[
                DiscoveredDataset(
                    state=DatasetStates.ATTACHED,
                    dataset_id=self.DATASET_ID,
                    blockdevice_id=_create_blockdevice_id_for_test(
                        self.DATASET_ID),
                    maximum_size=int(REALISTIC_BLOCKDEVICE_SIZE.to_Byte()),
                    device_path=FilePath(b"/dev/sda"),
                ),
            ],

        )

    def test_deleted_dataset_volume_no_filesystem(self):
        """
        If the configuration indicates a dataset with a primary manifestation
        on the node has been deleted and the volume associated with that
        dataset is attached but has no filesystem,
        ``BlockDeviceDeployer.calculate_changes`` returns a ``DetachVolume``
        state change operation.
        """
        local_state = self.ONE_DATASET_STATE
        local_config = to_node(local_state).transform(
            ["manifestations", unicode(self.DATASET_ID), "dataset", "deleted"],
            True
        )
        # Remove the manifestation and its mount path.
        local_state = local_state.transform(
            ['manifestations', unicode(self.DATASET_ID)],
            discard
        )
        local_state = local_state.transform(
            ['paths', unicode(self.DATASET_ID)],
            discard
        )
        device = FilePath(b"/dev/sda")

        # Local state shows that there is a device for the (now) non-manifest
        # dataset. i.e it is attached.
        self.assertEqual([self.DATASET_ID], local_state.devices.keys())
        assert_calculated_changes(
            case=self,
            node_state=local_state,
            node_config=local_config,
            # The unmounted dataset has been added back to the non-manifest
            # datasets by discover_state.
            nonmanifest_datasets=[
                self.MANIFESTATION.dataset
            ],
            expected_changes=in_parallel(
                changes=[
                    DetachVolume(
                        dataset_id=self.DATASET_ID,
                        blockdevice_id=self.BLOCKDEVICE_ID,
                    )
                ]
            ),
            discovered_datasets=[
                DiscoveredDataset(
                    state=DatasetStates.ATTACHED_NO_FILESYSTEM,
                    dataset_id=self.DATASET_ID,
                    blockdevice_id=_create_blockdevice_id_for_test(
                        self.DATASET_ID),
                    maximum_size=int(REALISTIC_BLOCKDEVICE_SIZE.to_Byte()),
                    device_path=device,
                ),
            ],

        )


class BlockDeviceDeployerAttachCalculateChangesTests(
        SynchronousTestCase, ScenarioMixin
):
    """
    Tests for ``BlockDeviceDeployer.calculate_changes`` in the cases relating
    to attaching existing datasets.
    """
    def test_attach_existing_nonmanifest(self):
        """
        If a dataset exists but is not manifest anywhere in the cluster and the
        configuration specifies it should be manifest on the deployer's node,
        ``BlockDeviceDeployer.calculate_changes`` returns state changes to
        attach that dataset to its node and then mount its filesystem.
        """
        deployer = create_blockdevicedeployer(
            self, hostname=self.NODE, node_uuid=self.NODE_UUID
        )
        # Give it a configuration that says a dataset should have a
        # manifestation on the deployer's node.
        node_config = to_node(self.ONE_DATASET_STATE)
        cluster_config = Deployment(nodes={node_config})

        # Give the node an empty state.
        node_state = self.ONE_DATASET_STATE.transform(
            ["manifestations", unicode(self.DATASET_ID)], discard
        ).transform(
            ["devices", self.DATASET_ID], discard
        )

        # Take the dataset in the configuration and make it part of the
        # cluster's non-manifest datasets state.
        manifestation = node_config.manifestations[unicode(self.DATASET_ID)]
        dataset = manifestation.dataset
        nonmanifest_datasets = {
            unicode(dataset.dataset_id): dataset,
        }
        cluster_state = DeploymentState(
            nodes={node_state},
            nonmanifest_datasets=nonmanifest_datasets,
        )

        local_state = local_state_from_shared_state(
            node_state=node_state,
            nonmanifest_datasets=cluster_state.nonmanifest_datasets,
        )
        changes = deployer.calculate_changes(
            cluster_config, cluster_state, local_state)
        self.assertEqual(
            in_parallel(changes=[
                AttachVolume(
                    dataset_id=UUID(dataset.dataset_id),
                    blockdevice_id=_create_blockdevice_id_for_test(
                        dataset.dataset_id)
                ),
            ]),
            changes
        )


class BlockDeviceDeployerMountCalculateChangesTests(
    SynchronousTestCase, ScenarioMixin
):
    """
    Tests for ``BlockDeviceDeployer.calculate_changes`` in the cases relating
    to mounting of filesystems.
    """
    def test_mount_manifestation(self):
        """
        If the volume for a dataset is attached to the node but the filesystem
        is not mounted and the configuration says the dataset is meant to be
        manifest on the node, ``BlockDeviceDeployer.calculate_changes`` returns
        a state change to mount the filesystem.
        """
        # Give it a state that says the volume is attached but nothing is
        # mounted.
        device = FilePath(b"/dev/sda")
        node_state = self.ONE_DATASET_STATE.set(
            manifestations={},
            paths={},
            devices={self.DATASET_ID: device},
        )

        # Give it a configuration that says there should be a manifestation.
        node_config = to_node(self.ONE_DATASET_STATE)

        assert_calculated_changes(
            self, node_state, node_config,
            {Dataset(dataset_id=unicode(self.DATASET_ID),
                     maximum_size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE)},
            in_parallel(changes=[
                MountBlockDevice(
                    dataset_id=self.DATASET_ID,
                    blockdevice_id=self.BLOCKDEVICE_ID,
                    mountpoint=FilePath(b"/flocker/").child(
                        bytes(self.DATASET_ID)
                    )
                ),
            ]),
            discovered_datasets=[
                DiscoveredDataset(
                    state=DatasetStates.ATTACHED,
                    dataset_id=self.DATASET_ID,
                    blockdevice_id=_create_blockdevice_id_for_test(
                        self.DATASET_ID),
                    maximum_size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE,
                    device_path=device,
                ),
            ],

        )


class BlockDeviceDeployerCreateFilesystemCalculateChangesTests(
    SynchronousTestCase, ScenarioMixin
):
    """
    Tests for ``BlockDeviceDeployer.calculate_changes`` in the cases relating
    to creation of filesystems.
    """
    def test_create_filesystem(self):
        """
        If the volume for a dataset is attached to the node but the filesystem
        does not exist and the configuration says the dataset is meant to be
        manifest on the node, ``BlockDeviceDeployer.calculate_changes`` returns
        a state change to create the filesystem.
        """
        # Give it a state that says the volume is attached but nothing is
        # mounted.
        device = FilePath(b"/dev/sda")
        node_state = self.ONE_DATASET_STATE.set(
            manifestations={},
            paths={},
            devices={self.DATASET_ID: device},
        )

        # Give it a configuration that says there should be a manifestation.
        node_config = to_node(self.ONE_DATASET_STATE)

        assert_calculated_changes(
            self, node_state, node_config,
            {Dataset(dataset_id=unicode(self.DATASET_ID),
                     maximum_size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE)},
            in_parallel(changes=[
                CreateFilesystem(device=device, filesystem=u"ext4")
            ]),
            discovered_datasets=[
                DiscoveredDataset(
                    state=DatasetStates.ATTACHED_NO_FILESYSTEM,
                    dataset_id=self.DATASET_ID,
                    blockdevice_id=_create_blockdevice_id_for_test(
                        self.DATASET_ID),
                    maximum_size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE,
                    device_path=device,
                ),
            ],
        )


class BlockDeviceDeployerUnmountCalculateChangesTests(
    SynchronousTestCase, ScenarioMixin
):
    """
    Tests for ``BlockDeviceDeployer.calculate_changes`` in the cases relating
    to unmounting of filesystems.
    """
    def test_unmount_manifestation(self):
        """
        If the filesystem for a dataset is mounted on the node and the
        configuration says the dataset is not meant to be manifest on that
        node, ``BlockDeviceDeployer.calculate_changes`` returns a state change
        to unmount the filesystem.
        """
        # Give it a state that says it has a manifestation of the dataset.
        node_state = self.ONE_DATASET_STATE

        # Give it a configuration that says it shouldn't have that
        # manifestation.
        node_config = to_node(self.ONE_DATASET_STATE).transform(
            ["manifestations", unicode(self.DATASET_ID)], discard
        )

        assert_calculated_changes(
            self, node_state, node_config, set(),
            in_parallel(changes=[
                UnmountBlockDevice(dataset_id=self.DATASET_ID,
                                   blockdevice_id=self.BLOCKDEVICE_ID)
            ])
        )

    def test_unmount_deleted_manifestation(self):
        """
        If the filesystem for a dataset is mounted on the node and the
        configuration says the dataset is deleted on that node,
        ``BlockDeviceDeployer.calculate_changes`` returns a state change to
        unmount the filesystem.
        """
        # Give it a state that says it has a manifestation of the dataset.
        node_state = self.ONE_DATASET_STATE

        # Give it a configuration that says it shouldn't have that
        # manifestation.
        node_config = to_node(self.ONE_DATASET_STATE).transform(
            ["manifestations", unicode(self.DATASET_ID),
             "dataset", "deleted"], True,
        )

        assert_calculated_changes(
            self, node_state, node_config, set(),
            in_parallel(changes=[
                UnmountBlockDevice(dataset_id=self.DATASET_ID,
                                   blockdevice_id=self.BLOCKDEVICE_ID)
            ])
        )

    def test_no_unmount_if_in_use(self):
        """
        If a dataset should be unmounted *and* it is in use by an application,
        no changes are made.
        """
        # State has a dataset in use by application
        local_state = add_application_with_volume(self.ONE_DATASET_STATE)

        # Give it a configuration that says it shouldn't have that
        # manifestation.
        node_config = to_node(self.ONE_DATASET_STATE).transform(
            ["manifestations", unicode(self.DATASET_ID)], discard
        )

        assert_calculated_changes(
            self, local_state, node_config, set(),
            in_parallel(changes=[]),
        )

    def test_no_unmount_if_leased(self):
        """
        If a dataset should be unmounted *and* it is leased on this node, no
        changes are made.
        """
        # State has a dataset which is leased
        local_state = self.ONE_DATASET_STATE
        leases = Leases().acquire(datetime.now(tz=UTC), self.DATASET_ID,
                                  self.ONE_DATASET_STATE.uuid)

        # Give it a configuration that says it shouldn't have that
        # manifestation.
        node_config = to_node(self.ONE_DATASET_STATE).transform(
            ["manifestations", unicode(self.DATASET_ID)], discard
        )

        assert_calculated_changes(
            self, local_state, node_config, set(),
            in_parallel(changes=[]), leases=leases,
        )

    def test_unmount_manifestation_when_leased_elsewhere(self):
        """
        If the filesystem for a dataset is mounted on the node and the
        configuration says the dataset is not meant to be manifest on that
        node, ``BlockDeviceDeployer.calculate_changes`` returns a state
        change to unmount the filesystem even if there is a lease, as long
        as the lease is for another node.
        """
        # Give it a state that says it has a manifestation of the dataset.
        node_state = self.ONE_DATASET_STATE
        leases = Leases().acquire(datetime.now(tz=UTC), self.DATASET_ID,
                                  uuid4())

        # Give it a configuration that says it shouldn't have that
        # manifestation.
        node_config = to_node(self.ONE_DATASET_STATE).transform(
            ["manifestations", unicode(self.DATASET_ID)], discard
        )

        assert_calculated_changes(
            self, node_state, node_config, set(),
            in_parallel(changes=[
                UnmountBlockDevice(dataset_id=self.DATASET_ID,
                                   blockdevice_id=self.BLOCKDEVICE_ID)
            ]), leases=leases,
        )


class BlockDeviceDeployerCreationCalculateChangesTests(
        SynchronousTestCase,
        ScenarioMixin
):
    """
    Tests for ``BlockDeviceDeployer.calculate_changes`` in the cases relating
    to dataset creation.
    """
    def test_no_devices_no_local_datasets(self):
        """
        If no devices exist and no datasets are part of the configuration for
        the deployer's node, no state changes are calculated.
        """
        dataset_id = unicode(uuid4())
        manifestation = Manifestation(
            dataset=Dataset(dataset_id=dataset_id), primary=True
        )
        node = u"192.0.2.1"
        node_uuid = uuid4()
        other_node = u"192.0.2.2"
        other_node_uuid = uuid4()
        configuration = Deployment(
            nodes={
                Node(
                    hostname=other_node,
                    uuid=other_node_uuid,
                    manifestations={dataset_id: manifestation},
                )
            }
        )
        state = DeploymentState(nodes=[])
        deployer = create_blockdevicedeployer(
            self, hostname=node, node_uuid=node_uuid
        )
        local_state = local_state_from_shared_state(
            node_state=state.get_node(node_uuid, hostname=node),
            nonmanifest_datasets={},
        )
        changes = deployer.calculate_changes(configuration, state, local_state)
        self.assertEqual(in_parallel(changes=[]), changes)

    def test_no_devices_one_dataset(self):
        """
        If no devices exist but a dataset is part of the configuration for the
        deployer's node, a ``CreateBlockDeviceDataset`` change is calculated.
        """
        uuid = uuid4()
        dataset_id = unicode(uuid4())
        dataset = Dataset(
            dataset_id=dataset_id,
            maximum_size=int(GiB(1).to_Byte().value)
        )
        manifestation = Manifestation(
            dataset=dataset, primary=True
        )
        node = u"192.0.2.1"
        configuration = Deployment(
            nodes={
                Node(
                    uuid=uuid,
                    manifestations={dataset_id: manifestation},
                )
            }
        )
        state = DeploymentState(nodes=[NodeState(
            uuid=uuid, hostname=node, applications=[], manifestations={},
            devices={}, paths={})])
        deployer = create_blockdevicedeployer(
            self, hostname=node, node_uuid=uuid,
        )
        local_state = local_state_from_shared_state(
            node_state=state.get_node(uuid),
            nonmanifest_datasets={},
        )
        changes = deployer.calculate_changes(configuration, state, local_state)
        self.assertEqual(
            in_parallel(
                changes=[
                    CreateBlockDeviceDataset(
                        dataset_id=UUID(dataset_id),
                        maximum_size=int(GiB(1).bytes)
                    )
                ]),
            changes
        )

    def test_dataset_elsewhere(self):
        """
        If block device is attached elsewhere but is part of the configuration
        for the deployer's node, ``calculate_changes`` does not
        attempt to create a new dataset.
        """
        uuid = uuid4()
        dataset_id = uuid4()
        maximum_size = int(GiB(1).bytes)
        dataset = Dataset(
            dataset_id=unicode(dataset_id),
            maximum_size=maximum_size,
        )
        manifestation = Manifestation(
            dataset=dataset, primary=True
        )
        node = u"192.0.2.1"
        configuration = Deployment(
            nodes={
                Node(
                    uuid=uuid,
                    manifestations={unicode(dataset_id): manifestation},
                )
            }
        )
        node_state = NodeState(
            uuid=uuid, hostname=node, applications=[], manifestations={},
            devices={}, paths={})
        state = DeploymentState(nodes={node_state})
        deployer = create_blockdevicedeployer(
            self, hostname=node, node_uuid=uuid,
        )
        local_state = BlockDeviceDeployerLocalState(
            node_uuid=uuid,
            hostname=node,
            datasets=dataset_map_from_iterable([
                DiscoveredDataset(
                    state=DatasetStates.ATTACHED_ELSEWHERE,
                    dataset_id=dataset_id,
                    maximum_size=maximum_size,
                    blockdevice_id=_create_blockdevice_id_for_test(dataset_id),
                ),
            ]),
        )
        changes = deployer.calculate_changes(configuration, state, local_state)
        self.assertEqual(
            in_parallel(changes=[ActionNeeded(dataset_id=dataset_id)]),
            changes
        )

    def _calculate_changes(self, local_uuid, local_hostname, local_state,
                           desired_configuration):
        """
        Create a ``BlockDeviceDeployer`` and call its
        ``calculate_changes`` method with the given arguments and an empty
        cluster state.

        :param UUID local_uuid: The node identifier to give the to the
            ``BlockDeviceDeployer``.
        :param unicode local_hostname: The node IP to give to the
            ``BlockDeviceDeployer``.
        :param desired_configuration: As accepted by
            ``IDeployer.calculate_changes``.

        :return: The return value of ``BlockDeviceDeployer.calculate_changes``.
        """
        # It is expected that someone will have merged local state into cluster
        # state.
        current_cluster_state = DeploymentState(nodes={local_state})

        deployer = create_blockdevicedeployer(
            self, node_uuid=local_uuid, hostname=local_hostname,
        )

        local_state = local_state_from_shared_state(
            node_state=local_state,
            nonmanifest_datasets={},
        )
        return deployer.calculate_changes(
            desired_configuration, current_cluster_state, local_state)

    def test_match_configuration_to_state_of_datasets(self):
        """
        ``BlockDeviceDeployer.calculate_changes`` does not yield a
        ``CreateBlockDeviceDataset`` change if a dataset with the same ID
        exists with different metadata.
        """
        expected_hostname = u'192.0.2.123'
        expected_dataset_id = unicode(uuid4())

        local_state = NodeState(
            hostname=expected_hostname,
            uuid=uuid4(),
            paths={
                expected_dataset_id: FilePath(b"/flocker").child(
                    expected_dataset_id.encode("ascii")),
            },
            devices={
                UUID(expected_dataset_id): FilePath(b"/dev/loop0"),
            },
            manifestations={
                expected_dataset_id:
                Manifestation(
                    primary=True,
                    dataset=Dataset(
                        dataset_id=expected_dataset_id,
                        maximum_size=int(REALISTIC_BLOCKDEVICE_SIZE.to_Byte()),
                        # Dataset state will always have empty metadata and
                        # deleted will always be False.
                        metadata={},
                        deleted=False,
                    ),
                ),
            },
        )

        # Give the dataset some metadata in the configuration, thus diverging
        # it from the representation in local_state.
        desired_configuration = Deployment(nodes=[Node(
            hostname=expected_hostname,
            uuid=local_state.uuid,
            manifestations=local_state.manifestations.transform(
                (expected_dataset_id, "dataset", "metadata"),
                {u"name": u"my_volume"}
            ))])
        actual_changes = self._calculate_changes(
            local_state.uuid,
            expected_hostname,
            local_state,
            desired_configuration
        )

        expected_changes = in_parallel(changes=[])

        self.assertEqual(expected_changes, actual_changes)

    def test_dataset_with_metadata(self):
        """
        When supplied with a configuration containing a dataset with metadata
        size, ``BlockDeviceDeployer.calculate_changes`` returns a
        ``CreateBlockDeviceDataset`` with a dataset with that metadata.
        """
        node_id = uuid4()
        node_address = u"192.0.2.1"
        dataset_id = unicode(uuid4())

        requested_dataset = Dataset(
            dataset_id=dataset_id,
            maximum_size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE,
            metadata={u"some": u"metadata"},
        )

        configuration = Deployment(
            nodes={
                Node(
                    uuid=node_id,
                    manifestations={
                        dataset_id: Manifestation(
                            dataset=requested_dataset,
                            primary=True,
                        )
                    },
                )
            }
        )
        node_state = NodeState(
            uuid=node_id,
            hostname=node_address,
            applications=[],
            manifestations={},
            devices={},
            paths={},
        )
        changes = self._calculate_changes(
            node_id, node_address, node_state, configuration)
        self.assertEqual(
            in_parallel(
                changes=[
                    CreateBlockDeviceDataset(
                        dataset_id=UUID(dataset_id),
                        maximum_size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE,
                        metadata={u"some": u"metadata"},
                    )
                ]),
            changes
        )

    def test_dataset_without_maximum_size(self):
        """
        When supplied with a configuration containing a dataset with a null
        size, ``BlockDeviceDeployer.calculate_changes`` returns a
        ``CreateBlockDeviceDataset`` for a dataset with a size fixed to the
        minimum allowed Rackspace volume size.

        XXX: Make the default size configurable.  FLOC-2679
        """
        node_id = uuid4()
        node_address = u"192.0.2.1"
        dataset_id = unicode(uuid4())

        requested_dataset = Dataset(dataset_id=dataset_id, maximum_size=None)

        configuration = Deployment(
            nodes={
                Node(
                    uuid=node_id,
                    manifestations={
                        dataset_id: Manifestation(
                            dataset=requested_dataset,
                            primary=True
                        )
                    },
                )
            }
        )
        node_state = NodeState(
            uuid=node_id,
            hostname=node_address,
            applications=[],
            manifestations={},
            devices={},
            paths={},
        )
        state = DeploymentState(
            nodes={node_state},
        )
        deployer = create_blockdevicedeployer(
            self,
            hostname=node_address,
            node_uuid=node_id,
        )
        local_state = local_state_from_shared_state(
            node_state=node_state,
            nonmanifest_datasets={},
        )
        changes = deployer.calculate_changes(
            configuration, state, local_state)
        expected_size = int(RACKSPACE_MINIMUM_VOLUME_SIZE.to_Byte())
        self.assertEqual(
            in_parallel(
                changes=[
                    CreateBlockDeviceDataset(
                        dataset_id=UUID(dataset_id),
                        maximum_size=expected_size,
                    )
                ]),
            changes
        )

    def test_dataset_default_maximum_size_stable(self):
        """
        When supplied with a configuration containing a dataset with a null
        size and operating against state where a volume of the default size
        exists for that dataset, ``BlockDeviceDeployer.calculate_changes``
        returns no changes.
        """
        # The state has a manifestation with a concrete size (as it must have).
        local_state = self.ONE_DATASET_STATE
        # The configuration is the same except it lacks a size.
        local_config = to_node(local_state).transform(
            ["manifestations", unicode(self.DATASET_ID), "dataset",
             "maximum_size"],
            None,
        )

        assert_calculated_changes(
            self, local_state, local_config, set(), in_parallel(changes=[]),
        )


class BlockDeviceDeployerDetachCalculateChangesTests(
        SynchronousTestCase, ScenarioMixin
):
    def test_detach_manifestation(self):
        """
        ``BlockDeviceDeployer.calculate_changes`` recognizes a volume that is
        attached but not mounted which is not associated with a dataset
        configured to have a manifestation on the deployer's node and returns a
        state change to detach the volume.
        """
        # Give it a state that says it has no manifestations but it does have
        # some attached volumes.
        node_state = NodeState(
            uuid=self.NODE_UUID, hostname=self.NODE,
            applications={},
            manifestations={},
            devices={self.DATASET_ID: FilePath(b"/dev/xda")},
            paths={},
        )

        # Give it a configuration that says no datasets should be manifest on
        # the deployer's node.
        node_config = to_node(node_state)

        assert_calculated_changes(
            self, node_state, node_config,
            {Dataset(dataset_id=unicode(self.DATASET_ID))},
            in_parallel(changes=[
                DetachVolume(dataset_id=self.DATASET_ID,
                             blockdevice_id=self.BLOCKDEVICE_ID)
            ])
        )

    def test_detach_deleted_manifestation(self):
        """
        ``BlockDeviceDeployer.calculate_changes`` recognizes a volume that is
        attached but not mounted which is associated with a dataset configured
        to have a deleted manifestation on the deployer's node and returns a
        state change to detach the volume.
        """
        # Give it a state that says it has no manifestations but it does have
        # some attached volumes.
        node_state = NodeState(
            uuid=self.NODE_UUID, hostname=self.NODE,
            applications={},
            manifestations={},
            devices={self.DATASET_ID: FilePath(b"/dev/xda")},
            paths={},
        )

        # Give it a configuration that says the dataset should be deleted on
        # the deployer's node.
        node_config = Node(
            uuid=self.NODE_UUID, hostname=self.NODE,
            manifestations={
                unicode(self.DATASET_ID): Manifestation(
                    dataset=Dataset(
                        dataset_id=unicode(self.DATASET_ID),
                        deleted=True,
                    ),
                    primary=True,
                )
            },
        )

        assert_calculated_changes(
            self, node_state, node_config,
            {Dataset(dataset_id=unicode(self.DATASET_ID))},
            in_parallel(changes=[
                DetachVolume(dataset_id=self.DATASET_ID,
                             blockdevice_id=self.BLOCKDEVICE_ID)
            ])
        )


class BlockDeviceInterfaceTests(SynchronousTestCase):
    """
    Tests for ``IBlockDeviceAPI`` and ``IBlockDeviceAsyncAPI``.
    """
    def test_names(self):
        """
        The two interfaces have all of the same names defined.
        """
        self.assertItemsEqual(
            list(IBlockDeviceAPI.names()),
            list(IBlockDeviceAsyncAPI.names()),
        )

    def test_same_signatures(self):
        """
        Methods of the two interfaces all have the same signature.
        """
        def parts(method):
            return (
                method.positional, method.kwargs,
                method.required, method.varargs
            )

        names = list(IBlockDeviceAPI.names())
        self.assertItemsEqual(
            list(parts(IBlockDeviceAPI[name]) for name in names),
            list(parts(IBlockDeviceAsyncAPI[name]) for name in names),
        )


class BlockDeviceDeployerCalculateChangesTests(
        SynchronousTestCase, ScenarioMixin
):
    """
    Tests for ``BlockDeviceDeployer.calculate_changes``.
    """
    def setUp(self):
        self.expected_change = ControllableAction(
            result=succeed(None),
        )
        self.deployer = BlockDeviceDeployer(
            node_uuid=ScenarioMixin.NODE_UUID,
            hostname=ScenarioMixin.NODE,
            block_device_api=UnusableAPI(),
            calculator=RecordingCalculator(self.expected_change),
        )
        self.local_state = BlockDeviceDeployerLocalState(
            node_uuid=ScenarioMixin.NODE_UUID,
            hostname=ScenarioMixin.NODE,
            datasets={},
        )

    @given(
        discovered_datasets=lists(DISCOVERED_DATASET_STRATEGY).map(
            dataset_map_from_iterable),
    )
    def test_calculates_changes(self, discovered_datasets):
        """
        ``BlockDeviceDeployer.calculate_changes`` returns the changes
        calculated by calling the provided ``ICalculator``.
        """
        node_state = NodeState(
            hostname=ScenarioMixin.NODE,
            uuid=ScenarioMixin.NODE_UUID,
            applications=[],
        )
        node_config = to_node(node_state)

        assert_calculated_changes_for_deployer(
            self, self.deployer,
            node_state=node_state,
            node_config=node_config,
            nonmanifest_datasets=[],
            additional_node_states=set(),
            additional_node_config=set(),
            expected_changes=self.expected_change,
            local_state=self.local_state.transform(
                ["datasets"], discovered_datasets,
            ),
        )
        self.assertEqual(
            self.deployer.calculator.discovered_datasets,
            discovered_datasets,
        )

    def test_unknown_applications(self):
        """
        If applications are unknown, no changes are calculated.
        """
        # We're ignorant about application state:
        node_state = NodeState(
            hostname=ScenarioMixin.NODE,
            uuid=ScenarioMixin.NODE_UUID,
            applications=None,
        )
        node_config = to_node(node_state)

        return assert_calculated_changes_for_deployer(
            self, self.deployer,
            node_state=node_state,
            node_config=node_config,
            nonmanifest_datasets=[],
            additional_node_states=set(),
            additional_node_config=set(),
            expected_changes=NoOp(),
            local_state=self.local_state,
        )

    def test_another_node_ignorant(self):
        """
        If a different node is ignorant about its state, it is still possible
        to calculate state for the current node.
        """
        # We're ignorant about application state:
        node_state = NodeState(
            hostname=ScenarioMixin.NODE,
            uuid=ScenarioMixin.NODE_UUID,
            applications=[],
        )
        node_config = to_node(node_state)

        return assert_calculated_changes_for_deployer(
            self, self.deployer,
            node_state=node_state,
            node_config=node_config,
            nonmanifest_datasets=[],
            additional_node_states={
                NodeState(hostname=u"1.2.3.4", uuid=uuid4(),
                          applications=None),
            },
            additional_node_config=set(),
            expected_changes=self.expected_change,
            local_state=self.local_state,
        )


class IBlockDeviceAPITestsMixin(object):
    """
    Tests to perform on ``IBlockDeviceAPI`` providers.
    """
    this_node = None

    def _verify_volume_size(self, requested_size, expected_volume_size):
        """
        Assert the implementation of
        ``IBlockDeviceAPI.list_volumes`` returns ``BlockDeviceVolume``s
        with the ``expected_volume_size`` and that
        ``IBlockDeviceAPI.create_volume`` creates devices with an
        ``expected_device_size`` (expected_volume_size plus platform
        specific over allocation).

        A device is created and attached, then ``lsblk`` is used to
        measure the size of the block device, as reported by the
        kernel of the machine to which the device is attached.

        :param int requested_size: Requested size of created volume.
        :param int expected_size: Expected size of created device.
        """
        dataset_id = uuid4()
        # Create a new volume.
        volume = self.api.create_volume(
            dataset_id=dataset_id,
            size=requested_size,
        )
        # Attach it, so that we can measure its size, as reported by
        # the kernel of the machine to which it's attached.
        self.api.attach_volume(
            volume.blockdevice_id, attach_to=self.this_node,
        )
        # Reload the volume using ``IBlockDeviceAPI.list_volumes`` in
        # case the implementation hasn't verified that the requested
        # size has actually been stored.
        volume = get_blockdevice_volume(self.api, volume.blockdevice_id)

        device_path = self.api.get_device_path(volume.blockdevice_id).path

        command = [b"/bin/lsblk", b"--noheadings", b"--bytes",
                   b"--output", b"SIZE", device_path.encode("ascii")]
        command_output = check_output(command).split(b'\n')[0]
        device_size = int(command_output.strip().decode("ascii"))
        if self.device_allocation_unit is None:
            expected_device_size = expected_volume_size
        else:
            expected_device_size = allocated_size(
                self.device_allocation_unit, expected_volume_size
            )
        self.assertEqual(
            (expected_volume_size, expected_device_size),
            (volume.size, device_size)
        )

    def test_interface(self):
        """
        ``api`` instances provide ``IBlockDeviceAPI``.
        """
        self.assertTrue(
            verifyObject(IBlockDeviceAPI, self.api)
        )

    def test_compute_instance_id_unicode(self):
        """
        ``compute_instance_id`` returns a ``unicode`` string.
        """
        self.assertIsInstance(self.this_node, unicode)

    def test_compute_instance_id_nonempty(self):
        """
        ``compute_instance_id`` returns a non-empty string.
        """
        self.assertNotEqual(u"", self.this_node)

    def test_list_volume_empty(self):
        """
        ``list_volumes`` returns an empty ``list`` if no block devices have
        been created.
        """
        self.assertEqual([], self.api.list_volumes())

    def test_created_is_listed(self):
        """
        ``create_volume`` returns a ``BlockDeviceVolume`` that is returned by
        ``list_volumes``.
        """
        dataset_id = uuid4()
        new_volume = self.api.create_volume(
            dataset_id=dataset_id,
            size=self.minimum_allocatable_size)
        self.assertIn(new_volume, self.api.list_volumes())

    def test_listed_volume_attributes(self):
        """
        ``list_volumes`` returns ``BlockDeviceVolume`` s that have the
        same dataset_id and (maybe over-allocated size) as was passed
        to ``create_volume``.
        """
        expected_dataset_id = uuid4()

        self.api.create_volume(
            dataset_id=expected_dataset_id,
            size=self.minimum_allocatable_size,
        )
        [listed_volume] = self.api.list_volumes()

        self.assertEqual(
            (expected_dataset_id, self.minimum_allocatable_size),
            (listed_volume.dataset_id, listed_volume.size)
        )

    def test_created_volume_attributes(self):
        """
        ``create_volume`` returns a ``BlockDeviceVolume`` that has a dataset_id
        and a size.
        """
        expected_dataset_id = uuid4()

        new_volume = self.api.create_volume(
            dataset_id=expected_dataset_id,
            size=self.minimum_allocatable_size,
        )

        self.assertEqual(
            (expected_dataset_id, self.minimum_allocatable_size),
            (new_volume.dataset_id, new_volume.size)
        )

    def test_attach_unknown_volume(self):
        """
        An attempt to attach an unknown ``BlockDeviceVolume`` raises
        ``UnknownVolume``.
        """
        self.assertRaises(
            UnknownVolume,
            self.api.attach_volume,
            blockdevice_id=self.unknown_blockdevice_id,
            attach_to=self.this_node,
        )

    def test_device_size(self):
        """
        ``attach_volume`` results in a device with the expected size.
        """
        requested_size = self.minimum_allocatable_size
        self._verify_volume_size(
            requested_size=requested_size,
            expected_volume_size=requested_size
        )

    def test_attach_attached_volume(self):
        """
        An attempt to attach an already attached ``BlockDeviceVolume`` raises
        ``AlreadyAttachedVolume``.
        """
        dataset_id = uuid4()

        new_volume = self.api.create_volume(
            dataset_id=dataset_id,
            size=self.minimum_allocatable_size
        )
        attached_volume = self.api.attach_volume(
            new_volume.blockdevice_id, attach_to=self.this_node,
        )

        self.assertRaises(
            AlreadyAttachedVolume,
            self.api.attach_volume,
            blockdevice_id=attached_volume.blockdevice_id,
            attach_to=self.this_node,
        )

    def test_attach_elsewhere_attached_volume(self):
        """
        An attempt to attach a ``BlockDeviceVolume`` already attached to
        another host raises ``AlreadyAttachedVolume``.
        """
        # This is a hack.  We don't know any other IDs though.
        # https://clusterhq.atlassian.net/browse/FLOC-1839
        another_node = self.this_node + u"-different"

        new_volume = self.api.create_volume(
            dataset_id=uuid4(),
            size=self.minimum_allocatable_size
        )
        attached_volume = self.api.attach_volume(
            new_volume.blockdevice_id,
            attach_to=self.this_node,
        )

        self.assertRaises(
            AlreadyAttachedVolume,
            self.api.attach_volume,
            blockdevice_id=attached_volume.blockdevice_id,
            attach_to=another_node,
        )

    def test_attach_unattached_volume(self):
        """
        An unattached ``BlockDeviceVolume`` can be attached.
        """
        dataset_id = uuid4()
        new_volume = self.api.create_volume(
            dataset_id=dataset_id,
            size=self.minimum_allocatable_size
        )
        expected_volume = BlockDeviceVolume(
            blockdevice_id=new_volume.blockdevice_id,
            size=new_volume.size,
            attached_to=self.this_node,
            dataset_id=dataset_id
        )
        attached_volume = self.api.attach_volume(
            blockdevice_id=new_volume.blockdevice_id,
            attach_to=self.this_node,
        )
        self.assertEqual(expected_volume, attached_volume)

    def test_attached_volume_listed(self):
        """
        An attached ``BlockDeviceVolume`` is listed.
        """
        dataset_id = uuid4()
        new_volume = self.api.create_volume(
            dataset_id=dataset_id,
            size=self.minimum_allocatable_size
        )
        expected_volume = BlockDeviceVolume(
            blockdevice_id=new_volume.blockdevice_id,
            size=new_volume.size,
            attached_to=self.this_node,
            dataset_id=dataset_id,
        )
        self.api.attach_volume(
            blockdevice_id=new_volume.blockdevice_id,
            attach_to=self.this_node,
        )
        self.assertEqual([expected_volume], self.api.list_volumes())

    def test_list_attached_and_unattached(self):
        """
        ``list_volumes`` returns both attached and unattached
        ``BlockDeviceVolume``s.
        """
        new_volume1 = self.api.create_volume(
            dataset_id=uuid4(),
            size=self.minimum_allocatable_size
        )
        new_volume2 = self.api.create_volume(
            dataset_id=uuid4(),
            size=self.minimum_allocatable_size
        )
        attached_volume = self.api.attach_volume(
            blockdevice_id=new_volume2.blockdevice_id,
            attach_to=self.this_node,
        )
        self.assertItemsEqual(
            [new_volume1, attached_volume],
            self.api.list_volumes()
        )

    def test_multiple_volumes_attached_to_host(self):
        """
        ``attach_volume`` can attach multiple block devices to a single host.
        """
        volume1 = self.api.create_volume(
            dataset_id=uuid4(),
            size=self.minimum_allocatable_size
        )
        volume2 = self.api.create_volume(
            dataset_id=uuid4(),
            size=self.minimum_allocatable_size
        )
        attached_volume1 = self.api.attach_volume(
            volume1.blockdevice_id, attach_to=self.this_node,
        )
        attached_volume2 = self.api.attach_volume(
            volume2.blockdevice_id, attach_to=self.this_node,
        )

        self.assertItemsEqual(
            [attached_volume1, attached_volume2],
            self.api.list_volumes()
        )

    def test_get_device_path_unknown_volume(self):
        """
        ``get_device_path`` raises ``UnknownVolume`` if the supplied
        ``blockdevice_id`` has not been created.
        """
        unknown_blockdevice_id = self.unknown_blockdevice_id
        exception = self.assertRaises(
            UnknownVolume,
            self.api.get_device_path,
            unknown_blockdevice_id
        )
        self.assertEqual(unknown_blockdevice_id, exception.blockdevice_id)

    def test_get_device_path_unattached_volume(self):
        """
        ``get_device_path`` raises ``UnattachedVolume`` if the supplied
        ``blockdevice_id`` corresponds to an unattached volume.
        """
        new_volume = self.api.create_volume(
            dataset_id=uuid4(),
            size=self.minimum_allocatable_size
        )
        exception = self.assertRaises(
            UnattachedVolume,
            self.api.get_device_path,
            new_volume.blockdevice_id
        )
        self.assertEqual(new_volume.blockdevice_id, exception.blockdevice_id)

    def test_get_device_path_device(self):
        """
        ``get_device_path`` returns a ``FilePath`` to the device representing
        the attached volume.
        """
        new_volume = self.api.create_volume(
            dataset_id=uuid4(),
            size=self.minimum_allocatable_size
        )
        attached_volume = self.api.attach_volume(
            new_volume.blockdevice_id,
            attach_to=self.this_node,
        )
        device_path = self.api.get_device_path(attached_volume.blockdevice_id)
        self.assertTrue(
            device_path.isBlockDevice(),
            u"Not a block device. Path: {!r}".format(device_path)
        )

    def test_get_device_path_device_repeatable_results(self):
        """
        ``get_device_path`` returns the same ``FilePath`` for the volume device
        when called multiple times.
        """
        new_volume = self.api.create_volume(
            dataset_id=uuid4(),
            size=self.minimum_allocatable_size
        )
        attached_volume = self.api.attach_volume(
            new_volume.blockdevice_id,
            attach_to=self.this_node,
        )

        device_path1 = self.api.get_device_path(attached_volume.blockdevice_id)
        device_path2 = self.api.get_device_path(attached_volume.blockdevice_id)

        self.assertEqual(device_path1, device_path2)

    def test_destroy_unknown_volume(self):
        """
        ``destroy_volume`` raises ``UnknownVolume`` if the supplied
        ``blockdevice_id`` does not exist.
        """
        volume = self.api.create_volume(
            dataset_id=uuid4(),
            size=self.minimum_allocatable_size,
        )
        self.api.destroy_volume(volume.blockdevice_id)
        exception = self.assertRaises(
            UnknownVolume,
            self.api.destroy_volume, blockdevice_id=volume.blockdevice_id
        )
        self.assertEqual(exception.args, (volume.blockdevice_id,))

    def test_destroy_volume(self):
        """
        An unattached volume can be destroyed using ``destroy_volume``.
        """
        unrelated = self.api.create_volume(
            dataset_id=uuid4(),
            size=self.minimum_allocatable_size,
        )
        volume = self.api.create_volume(
            dataset_id=uuid4(),
            size=self.minimum_allocatable_size,
        )
        self.api.destroy_volume(volume.blockdevice_id)
        self.assertEqual([unrelated], self.api.list_volumes())

    def _destroyed_volume(self):
        """
        :return: A ``BlockDeviceVolume`` representing a volume which has been
            destroyed.
        """
        volume = self.api.create_volume(
            dataset_id=uuid4(), size=self.minimum_allocatable_size
        )
        self.api.destroy_volume(volume.blockdevice_id)
        return volume

    def test_destroy_destroyed_volume(self):
        """
        ``destroy_volume`` raises ``UnknownVolume`` if the supplied
        ``blockdevice_id`` was associated with a volume but that volume has
        been destroyed.
        """
        volume = self._destroyed_volume()
        exception = self.assertRaises(
            UnknownVolume,
            self.api.destroy_volume, blockdevice_id=volume.blockdevice_id
        )
        self.assertEqual(exception.args, (volume.blockdevice_id,))

    def test_detach_unknown_volume(self):
        """
        ``detach_volume`` raises ``UnknownVolume`` if the supplied
        ``blockdevice_id`` does not exist.
        """
        blockdevice_id = self.unknown_blockdevice_id
        exception = self.assertRaises(
            UnknownVolume,
            self.api.detach_volume, blockdevice_id=blockdevice_id
        )
        self.assertEqual(exception.args, (blockdevice_id,))

    def test_detach_detached_volume(self):
        """
        ``detach_volume`` raises ``UnattachedVolume`` if the supplied
        ``blockdevice_id`` is not attached to a host.
        """
        volume = self.api.create_volume(
            dataset_id=uuid4(), size=self.minimum_allocatable_size
        )
        exception = self.assertRaises(
            UnattachedVolume,
            self.api.detach_volume, volume.blockdevice_id
        )
        self.assertEqual(exception.args, (volume.blockdevice_id,))

    def test_detach_volume(self):
        """
        A volume that is attached becomes detached after ``detach_volume`` is
        called with its ``blockdevice_id``.
        """
        def fail_mount(device):
            mountpoint = FilePath(self.mktemp())
            mountpoint.makedirs()
            process = Popen(
                [b"mount", device_path.path, mountpoint.path],
                stdout=PIPE,
                stderr=STDOUT
            )
            output = process.stdout.read()
            process.wait()
            return output

        # Create an unrelated, attached volume that should be undisturbed.
        unrelated = self.api.create_volume(
            dataset_id=uuid4(), size=self.minimum_allocatable_size
        )
        unrelated = self.api.attach_volume(
            unrelated.blockdevice_id, attach_to=self.this_node
        )

        # Create the volume we'll detach.
        volume = self.api.create_volume(
            dataset_id=uuid4(), size=self.minimum_allocatable_size
        )
        volume = self.api.attach_volume(
            volume.blockdevice_id, attach_to=self.this_node
        )

        device_path = self.api.get_device_path(volume.blockdevice_id)

        attached_error = fail_mount(device_path)

        self.api.detach_volume(volume.blockdevice_id)

        self.assertEqual(
            {unrelated, volume.set(attached_to=None)},
            set(self.api.list_volumes())
        )

        detached_error = fail_mount(device_path)

        # Make an incredibly indirect assertion to try to demonstrate we've
        # successfully detached the device.  The volume never had a filesystem
        # initialized on it so we couldn't mount it before when it was
        # attached.  Now that it's detached we still shouldn't be able to mount
        # it - but the reason we can't mount it should have changed.
        #
        # This isn't particularly great, no.
        self.assertNotEqual(attached_error, detached_error)

    def test_reattach_detached_volume(self):
        """
        A volume that has been detached can be re-attached.
        """
        # Create the volume we'll detach.
        volume = self.api.create_volume(
            dataset_id=uuid4(), size=self.minimum_allocatable_size
        )
        attached_volume = self.api.attach_volume(
            volume.blockdevice_id, attach_to=self.this_node
        )
        self.api.detach_volume(volume.blockdevice_id)
        reattached_volume = self.api.attach_volume(
            volume.blockdevice_id, attach_to=self.this_node
        )
        self.assertEqual(
            (attached_volume, [attached_volume]),
            (reattached_volume, self.api.list_volumes())
        )

    def test_attach_destroyed_volume(self):
        """
        ``attach_volume`` raises ``UnknownVolume`` when called with the
        ``blockdevice_id`` of a volume which has been destroyed.
        """
        volume = self._destroyed_volume()
        exception = self.assertRaises(
            UnknownVolume,
            self.api.attach_volume, volume.blockdevice_id,
            attach_to=self.this_node,
        )
        self.assertEqual(exception.args, (volume.blockdevice_id,))

    def assert_foreign_volume(self, flocker_volume):
        """
        Assert that a volume does not belong to the API object under test.

        :param BlockDeviceVolume flocker_volume: A volume to check for
            membership.

        :raise: A test-failing exception if the volume is found in the list of
            volumes returned by the API object under test.

        :return: ``None`` if the volume is not found in the list of volumes
            returned by the API object under test.
        """
        self.assertNotIn(flocker_volume, self.api.list_volumes())


def make_iblockdeviceapi_tests(
        blockdevice_api_factory,
        minimum_allocatable_size,
        device_allocation_unit,
        unknown_blockdevice_id_factory
):
    """
    :param blockdevice_api_factory: A factory which will be called
        with the generated ``TestCase`` during the ``setUp`` for each
        test and which should return an implementation of
        ``IBlockDeviceAPI`` to be tested.
    :param int minimum_allocatable_size: The minumum block device size
        (in bytes) supported on the platform under test. This must be
        a multiple ``IBlockDeviceAPI.allocation_unit()``.
    :param int device_allocation_unit: A size interval (in ``bytes``)
        which the storage system is expected to allocate eg Cinder
        allows sizes to be supplied in GiB, but certain Cinder storage
        drivers may be constrained to create sizes with 8GiB
        intervals.
    :param unknown_blockdevice_id_factory: A factory which will be called
        with an an instance of the generated ``TestCase``, and should
        return a ``blockdevice_id`` which is valid but unknown, i.e. does
        not match any actual volume in the backend.

    :returns: A ``TestCase`` with tests that will be performed on the
       supplied ``IBlockDeviceAPI`` provider.
    """
    class Tests(IBlockDeviceAPITestsMixin, SynchronousTestCase):
        def setUp(self):
            self.api = blockdevice_api_factory(test_case=self)
            self.unknown_blockdevice_id = unknown_blockdevice_id_factory(self)
            check_allocatable_size(
                self.api.allocation_unit(),
                minimum_allocatable_size
            )
            self.minimum_allocatable_size = minimum_allocatable_size
            self.device_allocation_unit = device_allocation_unit
            self.this_node = self.api.compute_instance_id()

    return Tests


class IProfiledBlockDeviceAPITestsMixin(object):
    """
    Tests to perform on ``IProfiledBlockDeviceAPI`` providers.
    """
    def test_interface(self):
        """
        The API object provides ``IProfiledBlockDeviceAPI``.
        """
        self.assertTrue(
            verifyObject(IProfiledBlockDeviceAPI, self.api)
        )

    def test_profile_respected(self):
        """
        Verify no errors are raised when constructing volumes with the
        mandatory profiles.
        """
        for profile in (c.value for c in MandatoryProfiles.iterconstants()):
            dataset_id = uuid4()
            self.addCleanup(detach_destroy_volumes, self.api)
            self.api.create_volume_with_profile(dataset_id=dataset_id,
                                                size=self.dataset_size,
                                                profile_name=profile)


def make_iprofiledblockdeviceapi_tests(profiled_blockdevice_api_factory,
                                       dataset_size):
    """
    Create tests for classes that implement ``IProfiledBlockDeviceAPI``.

    :param profiled_blockdevice_api_factory: A factory that generates the
        ``IProfiledBlockDeviceAPI`` provider to test.

    :param dataset_size: The size in bytes of the datasets to be created for
        test.

    :returns: A ``TestCase`` with tests that will be performed on the
       supplied ``IProfiledBlockDeviceAPI`` provider.
    """
    class Tests(IProfiledBlockDeviceAPITestsMixin, SynchronousTestCase):
        def setUp(self):
            self.api = profiled_blockdevice_api_factory(self)
            self.dataset_size = dataset_size

    return Tests


class IBlockDeviceAsyncAPITestsMixin(object):
    """
    Tests to perform on ``IBlockDeviceAsyncAPI`` providers.
    """
    def test_interface(self):
        """
        The API object provides ``IBlockDeviceAsyncAPI``.
        """
        self.assertTrue(
            verifyObject(IBlockDeviceAsyncAPI, self.api)
        )


def make_iblockdeviceasyncapi_tests(blockdeviceasync_api_factory):
    """
    :return: A ``TestCase`` with tests that will be performed on the supplied
        ``IBlockDeviceAsyncAPI`` provider.  These tests are not exhaustive
        because we currently assume ``make_iblockdeviceapi_tests`` will be used
        on the wrapped object.
    """
    class Tests(IBlockDeviceAsyncAPITestsMixin, SynchronousTestCase):
        def setUp(self):
            self.api = blockdeviceasync_api_factory(test_case=self)

    return Tests


class SyncToThreadedAsyncAPIAdapterTests(
    make_iblockdeviceasyncapi_tests(
        lambda test_case:
            _SyncToThreadedAsyncAPIAdapter(
                _reactor=None,
                _threadpool=None,
                # Okay to bypass loopbackblockdeviceapi_for_test here as long
                # as we don't call any methods on the object.  This lets these
                # tests run even as non-root.
                _sync=LoopbackBlockDeviceAPI.from_path(
                    root_path=test_case.mktemp(),
                    compute_instance_id=u"sync-threaded-tests",
                )
            )
    )
):
    """
    Tests for ``_SyncToThreadedAsyncAPIAdapter``.
    """


def losetup_detach(device_file):
    """
    Detach the supplied loopback ``device_file``.
    """
    check_output(['losetup', '--detach', device_file.path])


def losetup_detach_all(root_path):
    """
    Detach all loop devices associated with files contained in ``root_path``.

    :param FilePath root_path: A directory in which to search for loop device
        backing files.
    """
    for device_file, backing_file in _losetup_list():
        try:
            backing_file.segmentsFrom(root_path)
        except ValueError:
            pass
        else:
            losetup_detach(device_file)


def loopbackblockdeviceapi_for_test(test_case, allocation_unit=None):
    """
    :returns: A ``LoopbackBlockDeviceAPI`` with a temporary root directory
        created for the supplied ``test_case``.
    """
    user_id = getuid()
    if user_id != 0:
        raise SkipTest(
            "``LoopbackBlockDeviceAPI`` uses ``losetup``, "
            "which requires root privileges. "
            "Required UID: 0, Found UID: {!r}".format(user_id)
        )

    root_path = test_case.mktemp()
    loopback_blockdevice_api = LoopbackBlockDeviceAPI.from_path(
        root_path=root_path,
        compute_instance_id=random_name(test_case),
        allocation_unit=allocation_unit,
    )
    test_case.addCleanup(detach_destroy_volumes, loopback_blockdevice_api)
    return loopback_blockdevice_api


class LoopbackBlockDeviceAPITests(
        make_iblockdeviceapi_tests(
            blockdevice_api_factory=partial(
                loopbackblockdeviceapi_for_test,
                allocation_unit=LOOPBACK_ALLOCATION_UNIT
            ),
            minimum_allocatable_size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE,
            device_allocation_unit=None,
            unknown_blockdevice_id_factory=lambda test: unicode(uuid4()),
        )
):
    """
    Interface adherence Tests for ``LoopbackBlockDeviceAPI``.
    """


class LoopbackBlockDeviceAPIConstructorTests(SynchronousTestCase):
    """
    Implementation specific constructor tests.
    """
    def test_from_path_creates_instance_id_if_not_provided(self):
        """
        Calling ``from_path`` with empty instance id creates an id.
        """
        loopback_blockdevice_api = LoopbackBlockDeviceAPI.from_path(
            root_path=b'',
        )
        id = loopback_blockdevice_api.compute_instance_id()
        self.assertIsInstance(id, unicode)
        self.assertNotEqual(u"", id)

    def test_unique_instance_id_if_not_provided(self):
        """
        Calling constructor with empty instance id creates a different
        id each time.
        """
        a = LoopbackBlockDeviceAPI.from_path(root_path=b'')
        b = LoopbackBlockDeviceAPI.from_path(root_path=b'')
        self.assertNotEqual(
            a.compute_instance_id(),
            b.compute_instance_id(),
        )


class LoopbackBlockDeviceAPIImplementationTests(SynchronousTestCase):
    """
    Implementation specific tests for ``LoopbackBlockDeviceAPI``.
    """
    def assertDirectoryStructure(self, directory):
        """
        Assert that the supplied ``directory`` has all the sub-directories
        required by ``LoopbackBlockDeviceAPI``.
        """
        attached_directory = directory.child(
            LoopbackBlockDeviceAPI._attached_directory_name
        )
        unattached_directory = directory.child(
            LoopbackBlockDeviceAPI._unattached_directory_name
        )

        LoopbackBlockDeviceAPI.from_path(
            root_path=directory.path,
            compute_instance_id=random_name(self),
        )

        self.assertTrue(
            (True, True),
            (attached_directory.exists(), unattached_directory.exists())
        )

    def setUp(self):
        self.api = loopbackblockdeviceapi_for_test(
            test_case=self,
            allocation_unit=LOOPBACK_ALLOCATION_UNIT,
        )
        self.minimum_allocatable_size = LOOPBACK_MINIMUM_ALLOCATABLE_SIZE

    def test_initialise_directories(self):
        """
        ``from_path`` creates a directory structure if it doesn't already
        exist.
        """
        directory = FilePath(self.mktemp()).child('loopback')
        self.assertDirectoryStructure(directory)

    def test_initialise_directories_attached_exists(self):
        """
        ``from_path`` uses existing attached directory if present.
        """
        directory = FilePath(self.mktemp())
        attached_directory = directory.child(
            LoopbackBlockDeviceAPI._attached_directory_name
        )
        attached_directory.makedirs()
        self.assertDirectoryStructure(directory)

    def test_initialise_directories_unattached_exists(self):
        """
        ``from_path`` uses existing unattached directory if present.
        """
        directory = FilePath(self.mktemp())
        unattached_directory = directory.child(
            LoopbackBlockDeviceAPI._unattached_directory_name
        )
        unattached_directory.makedirs()
        self.assertDirectoryStructure(directory)

    def test_create_sparse(self):
        """
        ``create_volume`` creates sparse files.
        """
        requested_size = self.minimum_allocatable_size
        volume = self.api.create_volume(
            dataset_id=uuid4(),
            size=requested_size,
        )
        allocated_size = volume.size
        size = get_size_info(self.api, volume)

        self.assertEqual(
            (0, allocated_size),
            (size.actual, size.reported)
        )

    def test_create_with_non_allocation_unit(self):
        """
        ``create_volume`` raises ``ValueError`` unless the supplied
        ``size`` is a multiple of
        ``IBlockDeviceAPI.allocated_unit()``.
        """
        self.assertRaises(
            ValueError,
            self.api.create_volume,
            dataset_id=uuid4(),
            size=self.minimum_allocatable_size + 1,
        )

    def test_list_unattached_volumes(self):
        """
        ``list_volumes`` returns a ``BlockVolume`` for each unattached volume
        file.
        """
        expected_size = self.minimum_allocatable_size
        expected_dataset_id = uuid4()
        blockdevice_volume = _blockdevicevolume_from_dataset_id(
            size=expected_size,
            dataset_id=expected_dataset_id,
        )
        with (self.api._root_path
              .child('unattached')
              .child(_backing_file_name(blockdevice_volume))
              .open('wb')) as f:
            f.truncate(expected_size)
        self.assertEqual([blockdevice_volume], self.api.list_volumes())

    def test_list_attached_volumes(self):
        """
        ``list_volumes`` returns a ``BlockVolume`` for each attached volume
        file.
        """
        expected_size = self.minimum_allocatable_size
        expected_dataset_id = uuid4()
        this_node = self.api.compute_instance_id()

        blockdevice_volume = _blockdevicevolume_from_dataset_id(
            size=expected_size,
            attached_to=this_node,
            dataset_id=expected_dataset_id,
        )

        host_dir = self.api._root_path.descendant([
            b'attached', this_node.encode("utf-8")
        ])
        host_dir.makedirs()
        filename = _backing_file_name(blockdevice_volume)
        with host_dir.child(filename).open('wb') as f:
            f.truncate(expected_size)

        self.assertEqual([blockdevice_volume], self.api.list_volumes())

    def test_stale_attachments(self):
        """
        If there are volumes in the ``LoopbackBlockDeviceAPI``\ 's "attached"
        directory that do not have a corresponding loopback device, one is
        created for them.
        """
        this_node = self.api.compute_instance_id()
        volume = self.api.create_volume(
            dataset_id=uuid4(), size=self.minimum_allocatable_size
        )
        unattached = self.api._root_path.descendant([
            b"unattached", _backing_file_name(volume),
        ])
        attached = self.api._root_path.descendant([
            b"attached", this_node.encode("utf-8"), _backing_file_name(volume),
        ])
        attached.parent().makedirs()
        unattached.moveTo(attached)

        self.assertNotEqual(
            None,
            self.api.get_device_path(volume.blockdevice_id),
        )

    def test_missing_instance_id(self):
        """
        ``compute_instance_id`` raises an error when it cannot return a valid
        instance ID.
        """
        root_path = None  # Unused in this code.
        api = LoopbackBlockDeviceAPI(root_path, compute_instance_id=None)
        e = self.assertRaises(UnknownInstanceID, api.compute_instance_id)
        self.assertEqual(
            'Could not find valid instance ID for %r' % (api,), str(e))


class LosetupListTests(SynchronousTestCase):
    """
    Tests for ``_losetup_list_parse``.
    """
    def test_parse_empty(self):
        """
        An empty list is returned if there are no devices listed.
        """
        self.assertEqual([], _losetup_list_parse('\n'))

    def test_parse_one_line(self):
        """
        A pair of FilePaths are returned for device_file and backing_file.
        """
        input_text = '\n'.join([
            '/dev/loop0: []: (/tmp/rjw)',
            ''
        ])
        self.assertEqual(
            [(FilePath('/dev/loop0'), FilePath('/tmp/rjw'))],
            _losetup_list_parse(input_text)
        )

    def test_parse_multiple_lines(self):
        """
        A pair of FilePaths is returned for every loopback device on the
        system.
        """
        input_text = '\n'.join([
            '/dev/loop0: []: (/tmp/rjw)',
            '/dev/loop1: []: (/usr/share/virtualbox/VBoxGuestAdditions.iso)',
            ''
        ])
        self.assertEqual(
            [(FilePath('/dev/loop0'), FilePath('/tmp/rjw')),
             (FilePath('/dev/loop1'),
              FilePath('/usr/share/virtualbox/VBoxGuestAdditions.iso'))],
            _losetup_list_parse(input_text)
        )

    def test_remove_deleted_suffix(self):
        """
        Devices marked as ``(deleted)`` are listed.
        """
        input_text = '\n'.join([
            '/dev/loop0: []: (/tmp/rjw (deleted))',
            ''
        ])
        self.assertEqual(
            [(FilePath('/dev/loop0'), FilePath('/tmp/rjw'))],
            _losetup_list_parse(input_text)
        )

    def test_remove_inode(self):
        """
        Devices listed with their inode number (when run as root) are listed.
        """
        input_text = ''.join([
            '/dev/loop0: [0038]:723801 (/tmp/rjw)',
        ])
        self.assertEqual(
            [(FilePath('/dev/loop0'), FilePath('/tmp/rjw'))],
            _losetup_list_parse(input_text)
        )


@implementer(IProfiledBlockDeviceAPI)
class FakeProfiledLoopbackBlockDeviceAPI(
        proxyForInterface(IBlockDeviceAPI, "_loopback_blockdevice_api")):
    """
    Fake implementation of ``IProfiledBlockDeviceAPI`` and ``IBlockDeviceAPI``
    on top of ``LoopbackBlockDeviceAPI``. Profiles are not actually
    implemented for loopback devices, but this fake is useful for testing the
    intermediate layers.

    :ivar _loopback_blockdevice_api: The underlying ``LoopbackBlockDeviceAPI``.
    :ivar pmap dataset_profiles: A pmap from blockdevice_id to desired profile
        at creation time.
    """
    def __init__(self, loopback_blockdevice_api):
        self._loopback_blockdevice_api = loopback_blockdevice_api
        self.dataset_profiles = pmap({})

    def create_volume_with_profile(self, dataset_id, size, profile_name):
        """
        Calls the underlying ``create_volume`` on
        ``_loopback_blockdevice_api``, but records the desired profile_name for
        the purpose of test validation.
        """
        volume = self._loopback_blockdevice_api.create_volume(
            dataset_id=dataset_id, size=size)
        self.dataset_profiles = self.dataset_profiles.set(
            volume.blockdevice_id, profile_name)
        return volume


def fakeprofiledloopbackblockdeviceapi_for_test(test_case,
                                                allocation_unit=None):
    """
    Constructs a ``FakeProfiledLoopbackBlockDeviceAPI`` for use in tests that
    want to verify functionality with an ``IProfiledBlockDeviceAPI`` provider.
    """
    return FakeProfiledLoopbackBlockDeviceAPI(
        loopback_blockdevice_api=loopbackblockdeviceapi_for_test(
            test_case, allocation_unit=allocation_unit))


class FakeProfiledLoopbackBlockDeviceIProfiledBlockDeviceTests(
    make_iprofiledblockdeviceapi_tests(
        partial(fakeprofiledloopbackblockdeviceapi_for_test,
                allocation_unit=LOOPBACK_ALLOCATION_UNIT),
        LOOPBACK_MINIMUM_ALLOCATABLE_SIZE
    )
):
    """
    ``IProfiledBlockDeviceAPI`` interface adherence Tests for
    ``FakeProfiledLoopbackBlockDevice``.
    """


def umount(unmount_target):
    """
    Unmount a filesystem.

    :param FilePath unmount_target: The device file that is mounted or
        mountpoint directory.
    """
    check_output(['umount', unmount_target.path])


def umount_all(root_path):
    """
    Unmount all devices with mount points contained in ``root_path``.

    :param FilePath root_path: A directory in which to search for mount points.
    """
    def is_under_root(path):
        try:
            FilePath(path).segmentsFrom(root_path)
        except ValueError:
            return False
        return True

    def create_umount_callable(partition):
        return lambda: umount(FilePath(partition.mountpoint))

    deferreds = list(
        retry_failure(reactor,
                      create_umount_callable(partition),
                      steps=[0.1] * CLEANUP_RETRY_LIMIT)
        for partition in psutil.disk_partitions()
        if is_under_root(partition.mountpoint))

    return gather_deferreds(deferreds)


def mountroot_for_test(test_case):
    """
    Create a mountpoint root directory and unmount any filesystems with mount
    points beneath that directory when the test exits.

    :param TestCase test_case: The ``TestCase`` which is being run.
    :returns: A ``FilePath`` for the newly created mount root.
    """
    mountroot = FilePath(test_case.mktemp())
    mountroot.makedirs()
    test_case.addCleanup(umount_all, mountroot)
    return mountroot


_ARBITRARY_VOLUME = BlockDeviceVolume(
    blockdevice_id=u"abcd",
    size=int(REALISTIC_BLOCKDEVICE_SIZE.to_Byte()),
    dataset_id=uuid4(),
)


def multistep_change_log(parent, children):
    """
    Create an Eliot logging validation function which asserts that the given
    parent action is logged with the given children actions.

    :param ActionType parent: The type of an action that will be required.
    :param list children: The types of actions will be required to appear as
        children of ``parent``.

    :return: A two-argument callable suitable for use with
        ``validate_logging``.
    """
    def verify(self, logger):
        [parent_action] = LoggedAction.of_type(logger.messages, parent)
        children_actions = [
            LoggedAction.of_type(logger.messages, child_action)[0]
            for child_action
            in children
        ]
        self.assertEqual(children_actions, parent_action.children)
    return verify


class CreateFilesystemInitTests(
    make_with_init_tests(
        CreateFilesystem,
        dict(device=FilePath(b"/dev/null"), filesystem=u"ext4"),
        dict(),
    )
):
    """
    Tests for ``CreateFilesystem`` initialization.
    """


class CreateFilesystemTests(
    make_istatechange_tests(
        CreateFilesystem,
        dict(device=FilePath(b"/dev/null"), filesystem=u"ext4"),
        dict(device=FilePath(b"/dev/null"), filesystem=u"btrfs"),
    )
):
    """
    Tests for ``CreateFilesystem``\ 's ``IStateChange`` implementation.

    See ``MountBlockDeviceTests`` for more ``CreateFilesystem`` tests.
    """


class MountBlockDeviceInitTests(
    make_with_init_tests(
        MountBlockDevice,
        dict(dataset_id=uuid4(), blockdevice_id=ARBITRARY_BLOCKDEVICE_ID,
             mountpoint=FilePath(b"/foo")),
        dict(),
    )
):
    """
    Tests for ``Mountblockdevice`` initialization.
    """


class _MountScenario(PClass):
    """
    Setup tools for the tests defined on ``MountBlockDeviceTests``.

    This class serves as a central point for the handful of separate pieces of
    state that go into setting up a situation where it might be possible to
    mount something.  It also provides helpers for performing some of the
    external system interactions that might be necessary (such as creating a
    volume on the backend and initializing it with a filesystem).

    The factoring is dictated primarily by what makes it easy to write the
    tests with minimal duplication, nothing more.

    :ivar host: An identifier for the node to which a newly created volume will
        be attached.
    :ivar dataset_id: The dataset identifier associated with the volume that
        will be created.
    :ivar filesystem_type: The name of the filesystem with which the volume
        will be initialized (eg ``u"ext2"``).
    :ivar api: The ``IBlockDeviceAPI`` provider which will be used to create
        and attach a new volume.
    :ivar volume: The volume which is created.
    :ivar deployer: The ``BlockDeviceDeployer`` which will be passed to the
        ``IStateChange`` provider's ``run`` method.
    :ivar mountpoint: The filesystem location where the mount will be
        attempted.
    """
    host = field(type=unicode)
    dataset_id = field(type=UUID)
    filesystem_type = field(type=unicode)
    api = field()
    volume = field(type=BlockDeviceVolume)
    deployer = field(type=BlockDeviceDeployer)
    mountpoint = field(type=FilePath)

    @classmethod
    def generate(cls, case, mountpoint):
        """
        Create a new ``_MountScenario``.

        The scenario comes with a newly created volume attached to
        ``self.host`` and with a new ``self.filesystem_type`` filesystem.

        :param TestCase case: The running test case, used for temporary path
            generation.
        :param FilePath mountpoint: The location at which the mount attempt
            will eventually be made.

        :return: A new ``_MountScenario`` with attributes describing all of the
            state which has been set up.
        """
        host = u"192.0.7.8"
        filesystem_type = u"ext4"
        dataset_id = uuid4()
        api = loopbackblockdeviceapi_for_test(case)
        volume = api.create_volume(
            dataset_id=dataset_id, size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE,
        )
        api.attach_volume(volume.blockdevice_id, host)

        deployer = BlockDeviceDeployer(
            node_uuid=uuid4(),
            hostname=host,
            block_device_api=api,
            mountroot=mountpoint.parent(),
        )

        return cls(
            host=host, dataset_id=dataset_id, filesystem_type=filesystem_type,
            api=api, volume=volume, deployer=deployer, mountpoint=mountpoint,
        )

    def create(self):
        """
        Create a filesystem on this scenario's volume.

        :return: A ``Deferred`` which fires when the filesystem has been
            created.
        """
        return run_state_change(
            CreateFilesystem(
                device=self.api.get_device_path(self.volume.blockdevice_id),
                filesystem=self.filesystem_type
            ),
            self.deployer,
        )


class MountBlockDeviceTests(
    make_istatechange_tests(
        MountBlockDevice,
        dict(dataset_id=uuid4(), blockdevice_id=ARBITRARY_BLOCKDEVICE_ID,
             mountpoint=FilePath(b"/foo")),
        dict(dataset_id=uuid4(), blockdevice_id=ARBITRARY_BLOCKDEVICE_ID_2,
             mountpoint=FilePath(b"/bar")),
    )
):
    """
    Tests for ``MountBlockDevice``\ 's ``IStateChange`` implementation, as
    well as ``CreateFilesystem`` testing.
    """
    def _run_test(self, mountpoint):
        """
        Verify that ``MountBlockDevice.run`` mounts the filesystem from the
        block device for the attached volume it is given.
        """
        scenario = _MountScenario.generate(self, mountpoint)
        self.successResultOf(scenario.create())

        change = MountBlockDevice(
            dataset_id=scenario.dataset_id,
            blockdevice_id=scenario.volume.blockdevice_id,
            mountpoint=scenario.mountpoint
        )
        return scenario, run_state_change(change, scenario.deployer)

    def _run_success_test(self, mountpoint):
        scenario, mount_result = self._run_test(mountpoint)
        self.successResultOf(mount_result)

        expected = (
            scenario.api.get_device_path(scenario.volume.blockdevice_id).path,
            mountpoint.path,
            scenario.filesystem_type,
        )
        mounted = list(
            (part.device, part.mountpoint, part.fstype)
            for part in psutil.disk_partitions()
        )
        self.assertIn(expected, mounted)
        return scenario

    def _make_mounted_filesystem(self, path_segment=b"mount-test"):
        mountpoint = mountroot_for_test(self).child(path_segment)
        scenario = self._run_success_test(mountpoint)
        return scenario, mountpoint

    def _mount(self, scenario, mountpoint):
        self.successResultOf(run_state_change(
            MountBlockDevice(dataset_id=scenario.dataset_id,
                             blockdevice_id=scenario.volume.blockdevice_id,
                             mountpoint=mountpoint),
            scenario.deployer))

    def test_run(self):
        """
        ``CreateFilesystem.run`` initializes a block device with a filesystem
        which ``MountBlockDevice.run`` can then mount.
        """
        mountroot = mountroot_for_test(self)
        mountpoint = mountroot.child(b"mount-test")
        self._run_success_test(mountpoint)

    def test_create_fails_on_mounted_filesystem(self):
        """
        Running ``CreateFilesystem`` on a filesystem mounted with
        ``MountBlockDevice`` fails in a non-destructive manner.
        """
        scenario, mountpoint = self._make_mounted_filesystem()
        afile = mountpoint.child(b"file")
        afile.setContent(b"data")
        # Try recreating mounted filesystem; this should fail.
        self.failureResultOf(scenario.create(), FilesystemExists)
        # Unmounting and remounting, but our data still exists:
        umount(mountpoint)
        self._mount(scenario, mountpoint)
        self.assertEqual(afile.getContent(), b"data")

    def test_create_fails_on_existing_filesystem(self):
        """
        Running ``CreateFilesystem`` on a block device that already has a file
        self.successResultOf(run_state_change(
            MountBlockDevice(dataset_id=scenario.dataset_id,
                             blockdevice_id=scenario.volume.blockdevice_id,
                             mountpoint=mountpoint),
            scenario.deployer))
        system fails with an exception and preserves the data.

        This is because mkfs is a destructive operation that will destroy any
        existing filesystem on that block device.
        """
        scenario, mountpoint = self._make_mounted_filesystem()
        afile = mountpoint.child(b"file")
        afile.setContent(b"data")
        # Unmount the filesystem
        umount(mountpoint)
        # Try recreating filesystem; this should fail.
        self.failureResultOf(scenario.create(), FilesystemExists)
        # Remounting should succeed.
        self._mount(scenario, mountpoint)
        self.assertEqual(afile.getContent(), b"data")

    def test_mountpoint_exists(self):
        """
        It is not an error if the mountpoint given to ``MountBlockDevice``
        already exists.
        """
        mountroot = mountroot_for_test(self)
        mountpoint = mountroot.child(b"mount-test")
        mountpoint.makedirs()
        self._run_success_test(mountpoint)

    def test_mountpoint_error(self):
        """
        If the mountpoint is unusable, for example because it is a regular file
        instead of a directory, ``MountBlockDevice.run`` returns a ``Deferred``
        that fires with a ``Failure`` given the reason.
        """
        mountroot = mountroot_for_test(self)
        intermediate = mountroot.child(b"mount-error-test")
        intermediate.setContent(b"collision")
        mountpoint = intermediate.child(b"mount-test")
        scenario, mount_result = self._run_test(mountpoint)

        failure = self.failureResultOf(mount_result, OSError)
        self.assertEqual(ENOTDIR, failure.value.errno)

    def test_mountpoint_permissions(self):
        """
        The mountpoint is world-writeable (since containers can run as any
        user), and its parent is only accessible as current user (for
        security).
        """
        mountroot = mountroot_for_test(self)
        mountpoint = mountroot.child(b"mount-test")
        self._run_success_test(mountpoint)
        self.assertEqual((mountroot.getPermissions().shorthand(),
                          mountpoint.getPermissions().shorthand()),
                         ('rwx------', 'rwxrwxrwx'))

    def test_new_is_empty(self):
        """
        A newly created filesystem is empty after being mounted.

        If it's not empty it might break some Docker images that assumes
        volumes start out empty.
        """
        mountpoint = mountroot_for_test(self).child(b"mount-test")
        self._run_success_test(mountpoint)
        self.assertEqual(mountpoint.children(), [])

    def test_remount(self):
        """
        It's possible to unmount and then remount an attached volume.
        """
        mountpoint = mountroot_for_test(self).child(b"mount-test")
        scenario = self._run_success_test(mountpoint)
        check_call([b"umount", mountpoint.path])
        self.successResultOf(run_state_change(
            MountBlockDevice(dataset_id=scenario.dataset_id,
                             blockdevice_id=scenario.volume.blockdevice_id,
                             mountpoint=scenario.mountpoint),
            scenario.deployer))

    def test_lost_found_deleted_remount(self):
        """
        If ``lost+found`` is recreated, remounting it removes it.
        """
        mountpoint = mountroot_for_test(self).child(b"mount-test")
        scenario = self._run_success_test(mountpoint)
        check_call([b"mklost+found"], cwd=mountpoint.path)
        check_call([b"umount", mountpoint.path])
        self.successResultOf(run_state_change(
            MountBlockDevice(dataset_id=scenario.dataset_id,
                             blockdevice_id=scenario.volume.blockdevice_id,
                             mountpoint=scenario.mountpoint),
            scenario.deployer))
        self.assertEqual(mountpoint.children(), [])

    def test_lost_found_not_deleted_if_other_files_exist(self):
        """
        If files other than ``lost+found`` exist in the filesystem,
        ``lost+found`` is not deleted.
        """
        mountpoint = mountroot_for_test(self).child(b"mount-test")
        scenario = self._run_success_test(mountpoint)
        mountpoint.child(b"file").setContent(b"stuff")
        check_call([b"mklost+found"], cwd=mountpoint.path)
        check_call([b"umount", mountpoint.path])
        self.successResultOf(run_state_change(
            MountBlockDevice(dataset_id=scenario.dataset_id,
                             blockdevice_id=scenario.volume.blockdevice_id,
                             mountpoint=scenario.mountpoint),
            scenario.deployer))
        self.assertItemsEqual(mountpoint.children(),
                              [mountpoint.child(b"file"),
                               mountpoint.child(b"lost+found")])

    def test_world_permissions_not_reset_if_other_files_exist(self):
        """
        If files exist in the filesystem, permissions are not reset when the
        filesystem is remounted.
        """
        mountpoint = mountroot_for_test(self).child(b"mount-test")
        scenario = self._run_success_test(mountpoint)
        mountpoint.child(b"file").setContent(b"stuff")
        check_call([b"umount", mountpoint.path])
        mountpoint.chmod(S_IRWXU)
        mountpoint.restat()
        self.successResultOf(run_state_change(
            MountBlockDevice(dataset_id=scenario.dataset_id,
                             blockdevice_id=scenario.volume.blockdevice_id,
                             mountpoint=scenario.mountpoint),
            scenario.deployer))
        self.assertEqual(mountpoint.getPermissions().shorthand(),
                         'rwx------')


class UnmountBlockDeviceInitTests(
    make_with_init_tests(
        record_type=UnmountBlockDevice,
        kwargs=dict(dataset_id=uuid4(),
                    blockdevice_id=ARBITRARY_BLOCKDEVICE_ID),
        expected_defaults=dict(),
    )
):
    """
    Tests for ``UnmountBlockDevice`` initialization.
    """


class UnmountBlockDeviceTests(
    make_istatechange_tests(
        UnmountBlockDevice,
        dict(dataset_id=uuid4(), blockdevice_id=ARBITRARY_BLOCKDEVICE_ID),
        dict(dataset_id=uuid4(), blockdevice_id=ARBITRARY_BLOCKDEVICE_ID_2),
    )
):
    """
    Tests for ``UnmountBlockDevice``.
    """
    @validate_logging(
        lambda self, logger:
            self.assertEqual(
                1,
                len(LoggedAction.of_type(
                    logger.messages, UNMOUNT_BLOCK_DEVICE
                ))
            )
    )
    def test_run(self, logger):
        """
        ``UnmountBlockDevice.run`` unmounts the filesystem / block device
        associated with the volume passed to it (association as determined by
        the deployer's ``IBlockDeviceAPI`` provider).
        """
        self.patch(blockdevice, "_logger", logger)

        node = u"192.0.2.1"
        dataset_id = uuid4()
        deployer = create_blockdevicedeployer(self, hostname=node)
        api = deployer.block_device_api
        volume = api.create_volume(
            dataset_id=dataset_id, size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE
        )
        volume = api.attach_volume(volume.blockdevice_id, node)
        device = api.get_device_path(volume.blockdevice_id)
        mountroot = mountroot_for_test(self)
        mountpoint = mountroot.child(unicode(dataset_id).encode("ascii"))
        mountpoint.makedirs()
        make_filesystem(device, block_device=True)
        check_output([b"mount", device.path, mountpoint.path])

        change = UnmountBlockDevice(dataset_id=dataset_id,
                                    blockdevice_id=volume.blockdevice_id)
        self.successResultOf(run_state_change(change, deployer))
        self.assertNotIn(
            device,
            list(
                FilePath(partition.device)
                for partition
                in psutil.disk_partitions()
            )
        )


class DetachVolumeInitTests(
    make_with_init_tests(
        record_type=DetachVolume,
        kwargs=dict(dataset_id=uuid4(),
                    blockdevice_id=ARBITRARY_BLOCKDEVICE_ID),
        expected_defaults=dict(),
    )
):
    """
    Tests for ``DetachVolume`` initialization.
    """


class DetachVolumeTests(
    make_istatechange_tests(
        DetachVolume,
        dict(dataset_id=uuid4(), blockdevice_id=ARBITRARY_BLOCKDEVICE_ID),
        dict(dataset_id=uuid4(), blockdevice_id=ARBITRARY_BLOCKDEVICE_ID_2),
    )
):
    """
    Tests for ``DetachVolume``.
    """
    def test_run(self):
        """
        ``DetachVolume.run`` uses the deployer's ``IBlockDeviceAPI`` to detach
        its volume from the deployer's node.
        """
        dataset_id = uuid4()
        deployer = create_blockdevicedeployer(self, hostname=u"192.0.2.1")
        api = deployer.block_device_api
        volume = api.create_volume(
            dataset_id=dataset_id, size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE
        )
        api.attach_volume(
            volume.blockdevice_id,
            attach_to=api.compute_instance_id(),
        )

        change = DetachVolume(dataset_id=dataset_id,
                              blockdevice_id=volume.blockdevice_id)
        self.successResultOf(run_state_change(change, deployer))

        [listed_volume] = api.list_volumes()
        self.assertIs(None, listed_volume.attached_to)


class DestroyVolumeInitTests(
    make_with_init_tests(
        DestroyVolume,
        dict(blockdevice_id=ARBITRARY_BLOCKDEVICE_ID),
        dict(),
    )
):
    """
    Tests for ``DestroyVolume`` initialization.
    """


class DestroyVolumeTests(
    make_istatechange_tests(
        DestroyVolume,
        dict(blockdevice_id=ARBITRARY_BLOCKDEVICE_ID),
        dict(blockdevice_id=ARBITRARY_BLOCKDEVICE_ID_2),
    )
):
    """
    Tests for ``DestroyVolume``.
    """
    def test_run(self):
        """
        ``DestroyVolume.run`` uses the deployer's ``IBlockDeviceAPI`` to
        destroy its volume.
        """
        node = u"192.0.2.1"
        dataset_id = uuid4()
        deployer = create_blockdevicedeployer(self, hostname=node)
        api = deployer.block_device_api
        volume = api.create_volume(
            dataset_id=dataset_id, size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE
        )

        change = DestroyVolume(blockdevice_id=volume.blockdevice_id)
        self.successResultOf(run_state_change(change, deployer))

        self.assertEqual([], api.list_volumes())


class CreateBlockDeviceDatasetInitTests(
    make_with_init_tests(
        CreateBlockDeviceDataset,
        dict(
            dataset_id=uuid4(),
            maximum_size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE,
            metadata={u"meta": u"data"},
        ),
        dict(metadata={}),
    )
):
    """
    Tests for ``CreateBlockDeviceDataset`` initialization.
    """


class CreateBlockDeviceDatasetInterfaceTests(
    make_istatechange_tests(
        CreateBlockDeviceDataset,
        lambda _uuid=uuid4(): dict(
            dataset_id=_uuid,
            maximum_size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE,
        ),
        lambda _uuid=uuid4(): dict(
            dataset_id=uuid4(),
            maximum_size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE,
        ),
    )
):
    """
    ``CreateBlockDeviceDataset`` interface adherance tests.
    """


class CreateBlockDeviceDatasetImplementationMixin(object):
    """
    Utility Mixin for ``CreateBlockDeviceDataset`` implementation tests.
    """

    def _create_blockdevice_dataset(self, dataset_id, maximum_size,
                                    metadata=pmap({})):
        """
        Call ``CreateBlockDeviceDataset.run`` with a ``BlockDeviceDeployer``.

        :param UUID dataset_id: The uuid4 identifier for the dataset which will
            be created.
        :param int maximum_size: The size, in bytes, of the dataset which will
            be created.
        :param pmap(unicode, unicode) metadata: The metadata for the dataset.

        :returns: A ``BlockDeviceVolume`` for the created volume.
        """
        change = CreateBlockDeviceDataset(
            dataset_id=dataset_id,
            maximum_size=maximum_size,
            metadata=metadata
        )

        run_state_change(change, self.deployer)

        [volume] = self.api.list_volumes()
        return volume


def make_createblockdevicedataset_mixin(profiled_api):
    """
    Constructs a base class for tests that verify the implementation of
    ``CreateBlockDeviceDataset``.

    This ``IStateChange`` needs to be tested in two configurations:

    1) With an ``IBlockDeviceAPI`` provider that does not provide
        ``IProfiledBlockDeviceAPI``.

    2) With an ``IBlockDeviceAPI`` that does provide
        ``IProfiledBlockDeviceAPI``.

    The mixin holds utility functions that are useful in both configurations,
    and takes care of initializing the two different versions of the API.

    :param bool profiled_api: True if you want self.api to be an implementation
        of ``IBlockDeviceAPI`` that provides ``IProfiledBlockDeviceAPI``. False
        if you want self.api not to provide ``IProfiledBlockDeviceAPI``.
    """
    class Mixin(CreateBlockDeviceDatasetImplementationMixin,
                SynchronousTestCase):
        def setUp(self):
            if profiled_api:
                self.api = fakeprofiledloopbackblockdeviceapi_for_test(
                    self,
                    allocation_unit=LOOPBACK_ALLOCATION_UNIT
                )
            else:
                self.api = loopbackblockdeviceapi_for_test(
                    self,
                    allocation_unit=LOOPBACK_ALLOCATION_UNIT
                )
            self.mountroot = mountroot_for_test(self)
            self.deployer = BlockDeviceDeployer(
                node_uuid=uuid4(),
                hostname=u"192.0.2.10",
                block_device_api=self.api,
                mountroot=self.mountroot
            )

    return Mixin


class CreateBlockDeviceDatasetImplementationTests(
    make_createblockdevicedataset_mixin(profiled_api=False)
):
    """
    ``CreateBlockDeviceDataset`` implementation tests for use with a backend
    that is not storage profile aware.
    """

    @capture_logging(
        assertHasAction, CREATE_BLOCK_DEVICE_DATASET, succeeded=False
    )
    def test_created_exists(self, logger):
        """
        ``CreateBlockDeviceDataset.run`` fails with ``DatasetExists`` if there
        is already a ``BlockDeviceVolume`` for the requested dataset.
        """
        self.patch(blockdevice, '_logger', logger)
        dataset_id = uuid4()

        # The a volume for the dataset already exists.
        existing_volume = self.api.create_volume(
            dataset_id,
            size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE
        )

        change = CreateBlockDeviceDataset(
            dataset_id=dataset_id,
            maximum_size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE
        )

        changing = run_state_change(change, self.deployer)

        failure = self.failureResultOf(changing, DatasetExists)
        self.assertEqual(
            existing_volume,
            failure.value.blockdevice
        )

    def test_run_create(self):
        """
        ``CreateBlockDeviceDataset.run`` uses the ``IDeployer``\ 's API object
        to create a new volume.
        """
        dataset_id = uuid4()
        volume = self._create_blockdevice_dataset(
            dataset_id=dataset_id,
            maximum_size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE,
        )

        expected_volume = _blockdevicevolume_from_dataset_id(
            dataset_id=dataset_id, attached_to=None,
            size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE,
        )

        self.assertEqual(expected_volume, volume)

    @capture_logging(assertHasMessage, CREATE_VOLUME_PROFILE_DROPPED)
    def test_run_create_profile_dropped(self, logger):
        """
        ``CreateBlockDeviceDataset.run`` uses the ``IDeployer``\ 's API object
        to create a new volume, and logs that profile dropped during creation
        if the backend does not provide ``IProfiledBlockDeviceAPI``.
        """
        self.assertFalse(
            IProfiledBlockDeviceAPI.providedBy(self.api),
            u"This test assumes the API does not provide "
            u"IProfiledBlockDeviceAPI. If the API now does provide that "
            u"interface, this test needs a bit of love.")
        dataset_id = uuid4()
        volume = self._create_blockdevice_dataset(
            dataset_id=dataset_id,
            maximum_size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE,
            metadata={PROFILE_METADATA_KEY: u"gold"}
        )

        expected_volume = _blockdevicevolume_from_dataset_id(
            dataset_id=dataset_id, attached_to=None,
            size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE,
        )

        self.assertEqual(expected_volume, volume)

    def test_run_create_round_up(self):
        """
        ``CreateBlockDeviceDataset.run`` rounds up the size if the
        requested size is less than ``allocation_unit``.
        """
        dataset_id = uuid4()
        volume_info = self._create_blockdevice_dataset(
            dataset_id=dataset_id,
            # Request a size which will force over allocation.
            maximum_size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE + 1,
        )
        expected_volume = _blockdevicevolume_from_dataset_id(
            dataset_id=dataset_id, attached_to=None,
            size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE + LOOPBACK_ALLOCATION_UNIT,
        )
        self.assertEqual(expected_volume, volume_info)


class CreateBlockDeviceDatasetProfiledImplementationTests(
    make_createblockdevicedataset_mixin(profiled_api=True)
):
    """
    ``CreateBlockDeviceDataset`` implementation tests with a driver that can
    handle storage profiles.
    """

    def test_run_create_profile(self):
        """
        ``CreateBlockDeviceDataset.run`` uses the ``IDeployer``\ 's API object
        to create a new volume, and logs that profile dropped during creation
        if the backend does not provide ``IProfiledBlockDeviceAPI``.
        """
        self.assertTrue(
            IProfiledBlockDeviceAPI.providedBy(self.api),
            u"This test assumes the API provides IProfiledBlockDeviceAPI. If "
            u"the API now does not provide that interface, this test needs a "
            u"bit of love.")
        dataset_id = uuid4()
        profile = u"gold"
        volume_info = self._create_blockdevice_dataset(
            dataset_id=dataset_id,
            maximum_size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE,
            metadata={u"clusterhq:flocker:profile": profile}
        )
        actual_profile = self.api.dataset_profiles[volume_info.blockdevice_id]

        expected_volume = _blockdevicevolume_from_dataset_id(
            dataset_id=dataset_id, attached_to=None,
            size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE,
        )
        self.assertEqual(
            dict(volume=expected_volume, profile=profile),
            dict(volume=volume_info, profile=actual_profile))


class AttachVolumeInitTests(
    make_with_init_tests(
        record_type=AttachVolume,
        kwargs=dict(dataset_id=uuid4(),
                    blockdevice_id=ARBITRARY_BLOCKDEVICE_ID),
        expected_defaults=dict(),
    )
):
    """
    Tests for ``AttachVolume`` initialization.
    """


class AttachVolumeTests(
    make_istatechange_tests(
        AttachVolume,
        dict(dataset_id=uuid4(), blockdevice_id=ARBITRARY_BLOCKDEVICE_ID),
        dict(dataset_id=uuid4(), blockdevice_id=ARBITRARY_BLOCKDEVICE_ID_2),
    )
):
    """
    Tests for ``AttachVolume``\ 's ``IStateChange`` implementation.
    """
    @validate_logging(assertHasAction, ATTACH_VOLUME, True)
    def test_run(self, logger):
        """
        ``AttachVolume.run`` attaches a volume to a host.
        """
        host = u"192.0.7.8"
        dataset_id = uuid4()
        deployer = create_blockdevicedeployer(self, hostname=host)
        api = deployer.block_device_api
        volume = api.create_volume(
            dataset_id=dataset_id, size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE
        )
        change = AttachVolume(dataset_id=dataset_id,
                              blockdevice_id=volume.blockdevice_id)
        self.patch(blockdevice, "_logger", logger)
        self.successResultOf(run_state_change(change, deployer))

        expected_volume = volume.set(
            attached_to=api.compute_instance_id()
        )
        self.assertEqual([expected_volume], api.list_volumes())

    def test_missing(self):
        """
        If no volume is associated with the ``AttachVolume`` instance's
        ``blockdevice_id``, the underlying ``IBlockDeviceAPI`` should fail with
        an ``UnknownVolume`` exception, and ``AttachVolume.run`` should return
        a ``Deferred`` that fires with a ``Failure`` wrapping that exception.
        """
        dataset_id = uuid4()
        deployer = create_blockdevicedeployer(self)
        bad_blockdevice_id = u'incorrect_blockdevice_id'
        change = AttachVolume(dataset_id=dataset_id,
                              blockdevice_id=bad_blockdevice_id)
        failure = self.failureResultOf(
            run_state_change(change, deployer), UnknownVolume
        )
        self.assertEqual(
            bad_blockdevice_id, failure.value.blockdevice_id
        )


class ActionNeededInitTests(
    make_with_init_tests(
        record_type=ActionNeeded,
        kwargs=dict(dataset_id=uuid4()),
        expected_defaults=dict(),
    )
):
    """
    Tests for ``ActionNeeded`` initialization.
    """


class ActionNeededTests(
    make_istatechange_tests(
        ActionNeeded,
        dict(dataset_id=uuid4()),
        dict(dataset_id=uuid4()),
    )
):
    """
    Tests for ``ActionNeeded``\ 's ``IStateChange`` implementation.
    """


class AllocatedSizeTypeTests(SynchronousTestCase):
    """
    Tests for type coercion of parameters supplied to
    ``allocated_size``.
    """
    def test_allocation_unit_float(self):
        """
        ``allocated_size`` returns ``int`` if the supplied
        ``allocation_unit`` is of type ``float``.
        """
        self.assertIsInstance(
            allocated_size(
                allocation_unit=10.0,
                requested_size=1
            ),
            int,
        )

    def test_requested_size_float(self):
        """
        ``allocated_size`` returns ``int`` if the supplied
        ``requested_size`` is of type ``float``.
        """
        self.assertIsInstance(
            allocated_size(
                allocation_unit=10,
                requested_size=1.0,
            ),
            int,
        )


class AllocatedSizeTestsMixin(object):
    """
    Tests for ``allocated_size``.
    """
    def test_size_is_allocation_unit(self):
        """
        ``allocated_size`` returns the ``requested_size`` when it
        exactly matches the ``allocation_unit``.
        """
        requested_size = self.allocation_unit
        expected_size = requested_size
        self.assertEqual(
            expected_size,
            allocated_size(self.allocation_unit, requested_size)
        )

    def test_size_is_multiple_of_allocation_unit(self):
        """
        ``allocated_size`` returns the ``requested_size`` when it
        is a multiple of the ``allocation_unit``.
        """
        requested_size = self.allocation_unit * 10
        expected_size = requested_size
        self.assertEqual(
            expected_size,
            allocated_size(self.allocation_unit, requested_size)
        )

    def test_round_up(self):
        """
        ``allocated_size`` returns next multiple of
        ``allocation_unit`` if ``requested_size`` is not a multiple of
        ``allocation_unit``.
        """
        requested_size = self.allocation_unit + 1
        expected_size = self.allocation_unit * 2
        self.assertEqual(
            expected_size,
            allocated_size(self.allocation_unit, requested_size)
        )


def make_allocated_size_tests(allocation_unit):
    """
    :param Bitmath allocation_unit: The allocation_unit.
    :return: A ``TestCase`` to run ``AllocatedSizeTestsMixin`` tests
        against the supplied ``allocation_unit``. The name of the test
        contains the classname of ``allocation_unit``.
    """
    class Tests(AllocatedSizeTestsMixin, SynchronousTestCase):
        def setUp(self):
            self.allocation_unit = int(allocation_unit.to_Byte().value)

    Tests.__name__ = (
        'AllocatedSize' + allocation_unit.__class__.__name__ + 'Tests'
    )
    return Tests


def _make_allocated_size_testcases():
    """
    Build test cases for some common allocation_units.
    """
    for unit in (Byte, MB, MiB, GB, GiB):
        for size in (1, 2, 4, 8):
            test_case = make_allocated_size_tests(unit(size))
            globals()[test_case.__name__] = test_case
_make_allocated_size_testcases()
del _make_allocated_size_testcases


class ProcessLifetimeCacheIBlockDeviceAPITests(
        make_iblockdeviceapi_tests(
            blockdevice_api_factory=lambda test_case: ProcessLifetimeCache(
                loopbackblockdeviceapi_for_test(
                    test_case, allocation_unit=LOOPBACK_ALLOCATION_UNIT
                )),
            minimum_allocatable_size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE,
            device_allocation_unit=None,
            unknown_blockdevice_id_factory=lambda test: unicode(uuid4()),
        )
):
    """
    Interface adherence Tests for ``ProcessLifetimeCache``.
    """


class CountingProxy(object):
    """
    Transparent proxy that counts the number of calls to methods of the
    wrapped object.

    :ivar _wrapped: Wrapped object.
    :ivar call_count: Mapping of (method name, args, kwargs) to number of
        calls.
    """
    def __init__(self, wrapped):
        self._wrapped = wrapped
        self.call_count = pmap()

    def num_calls(self, name, *args, **kwargs):
        """
        Return the number of times the given method was called with given
        arguments.

        :param name: Method name.
        :param args: Positional arguments it was called with.
        :param kwargs: Keyword arguments it was called with.

        :return: Number of calls.
        """
        return self.call_count.get(
            pvector([name, pvector(args), pmap(kwargs)]), 0)

    def __getattr__(self, name):
        method = getattr(self._wrapped, name)

        def counting_proxy(*args, **kwargs):
            key = pvector([name, pvector(args), pmap(kwargs)])
            current_count = self.call_count.get(key, 0)
            self.call_count = self.call_count.set(key, current_count + 1)
            return method(*args, **kwargs)
        return counting_proxy


class ProcessLifetimeCacheTests(SynchronousTestCase):
    """
    Tests for the caching logic in ``ProcessLifetimeCache``.
    """
    def setUp(self):
        self.api = loopbackblockdeviceapi_for_test(self)
        self.counting_proxy = CountingProxy(self.api)
        self.cache = ProcessLifetimeCache(self.counting_proxy)

    def test_compute_instance_id(self):
        """
        The result of ``compute_instance_id`` is cached indefinitely.
        """
        initial = self.cache.compute_instance_id()
        later = [self.cache.compute_instance_id() for i in range(10)]
        self.assertEqual(
            (later, self.counting_proxy.num_calls("compute_instance_id")),
            ([initial] * 10, 1))

    def attached_volumes(self):
        """
        :return: A sequence of two attached volumes' ``blockdevice_id``.
        """
        dataset1 = uuid4()
        dataset2 = uuid4()
        this_node = self.cache.compute_instance_id()
        attached_volume1 = self.cache.attach_volume(
            self.cache.create_volume(
                dataset_id=dataset1,
                size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE,
            ).blockdevice_id,
            attach_to=this_node)
        attached_volume2 = self.cache.attach_volume(
            self.cache.create_volume(
                dataset_id=dataset2,
                size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE,
            ).blockdevice_id,
            attach_to=this_node)
        return attached_volume1.blockdevice_id, attached_volume2.blockdevice_id

    def test_get_device_path_cached_after_attach(self):
        """
        The result of ``get_device_path`` is cached after an ``attach_device``.
        """
        attached_id1, attached_id2 = self.attached_volumes()
        path1 = self.cache.get_device_path(attached_id1)
        path2 = self.cache.get_device_path(attached_id2)
        path1again = self.cache.get_device_path(attached_id1)
        path2again = self.cache.get_device_path(attached_id2)

        self.assertEqual(
            (path1again, path2again,
             path1 == path2,
             self.counting_proxy.num_calls("get_device_path", attached_id1),
             self.counting_proxy.num_calls("get_device_path", attached_id2)),
            (path1, path2, False, 1, 1))

    def test_get_device_path_until_detach(self):
        """
        The result of ``get_device_path`` is no longer cached after an
        ``detach_device`` call.
        """
        attached_id1, attached_id2 = self.attached_volumes()
        # Warm up cache:
        self.cache.get_device_path(attached_id1)
        # Invalidate cache:
        self.cache.detach_volume(attached_id1)

        self.assertRaises(UnattachedVolume,
                          self.cache.get_device_path, attached_id1)


def make_icloudapi_tests(
        blockdevice_api_factory,
):
    """
    :param blockdevice_api_factory: A factory which will be called
        with the generated ``TestCase`` during the ``setUp`` for each
        test and which should return a provider of both ``IBlockDeviceAPI``
        and ``ICloudAPI`` to be tested.

    :returns: A ``TestCase`` with tests that will be performed on the
       supplied ``IBlockDeviceAPI``/``ICloudAPI`` provider.
    """
    class Tests(TestCase):
        def setUp(self):
            self.api = blockdevice_api_factory(test_case=self)
            self.this_node = self.api.compute_instance_id()
            self.async_cloud_api = _SyncToThreadedAsyncCloudAPIAdapter(
                _reactor=reactor, _sync=self.api,
                _threadpool=reactor.getThreadPool())

        def test_interface(self):
            """
            The result of the factory provides ``ICloudAPI``.
            """
            self.assertTrue(verifyObject(ICloudAPI, self.api))

        def test_current_machine_is_live(self):
            """
            The machine running the test is reported as alive.
            """
            d = self.async_cloud_api.list_live_nodes()
            d.addCallback(lambda live:
                          self.assertIn(self.api.compute_instance_id(), live))
            return d
    return Tests


def _surround_with_callbacks_decorator(method_name, callback, proxy_object):
    """
    Creates a method that proxies to ``getattr(proxy_object, method_name)`` and
    calls callback before and after.

    :param method_name: The name of the method that should be called.
    :param callback: The callback to call before and after calling the method.
    :param proxy_object: The object to proxy the invocation to.
    """

    def proxied_function(self, *args, **kwargs):
        method = getattr(proxy_object, method_name)
        callback()  # Before method call.
        result = method(*args, **kwargs)
        callback()  # After method call.
        return result

    return proxied_function


def create_callback_blockdevice_manager_proxy(proxy_object, callback):
    """
    Creates a provider of ``IBlockDeviceManager`` that proxies to another
    ``IBlockDeviceManager`` privider and calls a callback before and after
    each call to the underlying object. This enables tests where you want to
    inject code before or after any calls to the underlying API.

    :param proxy_object: The ``IBlockDeviceManager`` provider that is being
        proxied to.
    :param callback: The callback to be called before and after every call to a
        method of ``proxy_object``.
    """
    @interface_decorator("callback_blockdevice_manager",
                         IBlockDeviceManager,
                         _surround_with_callbacks_decorator,
                         callback,
                         proxy_object)
    class BlockDeviceManagerCallbackProxy(object):
        pass

    return BlockDeviceManagerCallbackProxy()
