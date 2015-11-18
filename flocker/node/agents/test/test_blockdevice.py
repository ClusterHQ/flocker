# Copyright ClusterHQ Ltd.  See LICENSE file for details.

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

from zope.interface import implementer
from zope.interface.verify import verifyObject

from pyrsistent import (
    PClass, PRecord, field, discard, pmap, pvector,
)

from twisted.internet.defer import succeed
from twisted.python.components import proxyForInterface
from twisted.python.constants import Names, NamedConstant
from twisted.python.runtime import platform
from twisted.python.filepath import FilePath
from twisted.trial.unittest import SynchronousTestCase, SkipTest

from eliot import start_action, write_traceback, Message, Logger
from eliot.testing import (
    validate_logging, capture_logging,
    LoggedAction, assertHasMessage, assertHasAction
)

from ..._change import LOG_SEQUENTIALLY
from .. import blockdevice
from ...test.istatechange import make_istatechange_tests
from ..blockdevice import (
    BlockDeviceDeployerLocalState, BlockDeviceDeployer,
    BlockDeviceCalculater,

    IBlockDeviceAPI, MandatoryProfiles, IProfiledBlockDeviceAPI,
    BlockDeviceVolume, UnknownVolume, AlreadyAttachedVolume,
    CreateBlockDeviceDataset, UnattachedVolume, DatasetExists,
    DestroyBlockDeviceDataset, UnmountBlockDevice, DetachVolume, AttachVolume,
    CreateFilesystem, DestroyVolume, MountBlockDevice, ActionNeeded,

    ICalculater,

    DiscoveredDataset, DesiredDataset, DatasetStates,

    PROFILE_METADATA_KEY,

    UNMOUNT_BLOCK_DEVICE, DETACH_VOLUME,
    DESTROY_VOLUME,
    CREATE_BLOCK_DEVICE_DATASET,
    INVALID_DEVICE_PATH,
    CREATE_VOLUME_PROFILE_DROPPED,
    DISCOVERED_RAW_STATE,

    IBlockDeviceAsyncAPI,
    _SyncToThreadedAsyncAPIAdapter,
    allocated_size,
    ProcessLifetimeCache,
    FilesystemExists,
    UnknownInstanceID,
    get_blockdevice_volume,
)

from ..loopback import (
    check_allocatable_size,
    LoopbackBlockDeviceAPI,
    _losetup_list_parse,
    _losetup_list, _blockdevicevolume_from_dataset_id,
    _backing_file_name,
)


from ... import run_state_change, in_parallel, ILocalState, NoOp, IStateChange
from ...testtools import (
    ideployer_tests_factory, to_node, assert_calculated_changes_for_deployer,
    ControllableAction,
)
from ....testtools import (
    REALISTIC_BLOCKDEVICE_SIZE, run_process, make_with_init_tests, random_name,
)
from ....control import (
    Dataset, Manifestation, Node, NodeState, Deployment, DeploymentState,
    NonManifestDatasets, Application, AttachedVolume, DockerImage
)
from ....control._model import Leases

# Move these somewhere else, write tests for them. FLOC-1774
from ....common.test.test_thread import NonThreadPool, NonReactor

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

if not platform.isLinux():
    # The majority of Flocker isn't supported except on Linux - this test
    # module just happens to run some code that obviously breaks on some other
    # platforms.  Rather than skipping each test module individually it would
    # be nice to have some single global solution.  FLOC-1560, FLOC-1205
    skip = "flocker.node.agents.blockdevice is only supported on Linux"


class _SizeInfo(PRecord):
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
        test_case, hostname=u"192.0.2.1", node_uuid=uuid4()
):
    """
    Create a new ``BlockDeviceDeployer``.

    :param unicode hostname: The hostname to assign the deployer.
    :param UUID node_uuid: The unique identifier of the node to assign the
        deployer.

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
    expected_volumes,
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
            datasets={
                dataset.dataset_id: dataset
                for dataset in expected_discovered_datasets
            },
            volumes=expected_volumes,
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
        assert_discovered_state(self, self.deployer, [], [])

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
            expected_volumes=[volume],
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
        attached_volume = self.api.attach_volume(
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
            expected_volumes=[attached_volume],
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
        attached_volume = self.api.attach_volume(
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
            expected_volumes=[attached_volume],
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

        attached_volume = self.api.attach_volume(
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
            expected_volumes=[attached_volume],
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
        attached_volume = self.api.attach_volume(
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
            expected_volumes=[attached_volume]
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
        ``BlockDeviceDeployer.discover_state`` does not report remotely
        attached volumes as datasets.
        """
        dataset_id = uuid4()
        volume = self.api.create_volume(
            dataset_id=dataset_id,
            size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE
        )
        attached_volume = self.api.attach_volume(
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
            expected_volumes=[attached_volume],
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
        attached_volume = self.api.attach_volume(
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
            expected_volumes=[attached_volume],
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
        attached_volume = self.api.attach_volume(
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
            expected_volumes=[attached_volume],
        )


@implementer(IBlockDeviceAPI)
class UnusableAPI(object):
    """
    A non-implementation of ``IBlockDeviceAPI`` where it is explicitly required
    that the object not be used for anything.
    """


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
            maximum_size=REALISTIC_BLOCKDEVICE_SIZE,
            metadata=METADATA,
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


def _infer_volumes_for_test(node_uuid, node_hostname, compute_instance_id,
                            cluster_state):
    """
    Infer the current ``BlockDeviceVolume`` instances in the cluster. This is
    for use by tests that create cluster_state by hand instead of using the API
    to actually construct the cluster.  The ``BlockDeviceVolume`` instances
    constructed with this function do not have blockdevice_ids that can be
    used with the ``IBlockDeviceAPI``. Note that this function is brittle and
    can easily become out of date with the ``discover_state`` implementation of
    ``BlockDeviceDeployer``.  The tests that create a cluster_state by hand
    would probably be better off actually using the API to construct a state
    so that this brittle function can be removed.

    If you are using the ``IBlockDeviceAPI`` to set up the cluster_state, just
    use api.list_volumes() instead of calling this function.

    :param UUID node_uuid: The uuid of the local node.

    :param unicode node_hostname: The hostname of the local node.

    :param unicode compute_instance_id: The value for the attached_to field of
        the ``BlockDeviceVolume`` instances that are created for manifestions
        on the local node.

    :param DeploymentState cluster_state: The rest of the cluster_state. This
        is inspected to determine the volumes that are not attached to any node
        (nonmanifest_datasets) and the volumes that are attached to remote
        nodes.

    :returns: A list of ``BlockDeviceVolume`` instances for all the volumes in
        cluster_state that is only suitable for use in tests that do not use
        the ``IBlockDeviceAPI`` to set up the cluster_state.
    """
    def create_test_blockdevice_volume_for_dataset_id(dataset_id,
                                                      attached_to=None):
        return BlockDeviceVolume(
            blockdevice_id=_create_blockdevice_id_for_test(dataset_id),
            size=REALISTIC_BLOCKDEVICE_SIZE,
            attached_to=attached_to,
            dataset_id=UUID(dataset_id))
    node_state = cluster_state.get_node(node_uuid,
                                        hostname=node_hostname)
    local_volumes = [
        create_test_blockdevice_volume_for_dataset_id(
            dataset_id, attached_to=compute_instance_id)
        for dataset_id in (node_state.manifestations or {})]

    nonmanifest_datasets = cluster_state.nonmanifest_datasets
    unattached_volumes = [
        create_test_blockdevice_volume_for_dataset_id(dataset_id)
        for dataset_id in (nonmanifest_datasets or {})]

    volumes = local_volumes + unattached_volumes

    for remote_node_state in cluster_state.nodes:
        if remote_node_state == node_state:
            # Skip this node for remote processing if it is the local node.
            continue
        # Construct a fake instance id for the attached_to field of the
        # ``BlockDeviceVolume`` instances that are connected to remote nodes.
        # This is an opaque identifier, and just needs to be different than
        # compute_instance_id for the sake of testing this node.
        fake_instance_id = u"remote_node_{}".format(
            unicode(remote_node_state.uuid))
        remote_volumes = [
            create_test_blockdevice_volume_for_dataset_id(
                dataset_id, attached_to=fake_instance_id)
            for dataset_id in (remote_node_state.manifestations or {})]

        volumes.extend(remote_volumes)
    return volumes


class DiscoverVolumesMethod(Names):
    """
    Constants for determining volumes in calculate_changes tests.

    :ivar GET_VOLUMES_FROM_API: Simply call ``list_volumes`` on the passed in
        API.
    :ivar INFER_VOLUMES_FROM_STATE: Call ``_infer_volumes_for_test`` to create
        a list of volumes from the manually constructed cluster_state.
    """
    GET_VOLUMES_FROM_API = NamedConstant()
    INFER_VOLUMES_FROM_STATE = NamedConstant()


@implementer(ICalculater)
class RecordingCalculater(object):
    def __init__(self, expected_changes):
        self.expected_changes = expected_changes

    def calculate_changes_for_datasets(
        self, discovered_datasets, desired_datasets,
    ):
        self.desired_datasets = desired_datasets
        return self.expected_changes


class CalculaterTests(SynchronousTestCase):
    def test_not_implemented_yet(self):
        self.fail("ICalculater implementations need to be verified.")


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
    Assert that ``calculate_changes`` calculates the given desired datasetsg
    invoked with the given state and configuration.

    :param TestCase test_case: The ``TestCase`` which is being run.
    :param BlockDeviceDeployer deployer: The deployer that will be asked to
        calculate the desired datasets.
    :param desired_manifeations: Manifestations to include in the local nodes
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
    calculater = RecordingCalculater(NoOp())
    deployer = deployer.set(calculater=calculater)
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
        calculater.desired_datasets,
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
            mountroot=mountroot_for_test(self),
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
        If there is a manifesation on this node, then the
        corresponding dataset has a desired state of ``MOUNTED``.
        """
        assert_desired_datasets(
            self, self.deployer,
            desired_manifestations=[ScenarioMixin.MANIFESTATION],
            expected_datasets=[
                DesiredDataset(
                    state=DatasetStates.MOUNTED,
                    dataset_id=ScenarioMixin.DATASET_ID,
                    metadata=ScenarioMixin.METADATA,
                    maximum_size=REALISTIC_BLOCKDEVICE_SIZE,
                    mount_point=self.deployer.mountroot.child(
                        unicode(ScenarioMixin.DATASET_ID)
                    ),
                ),
            ],
        )

    def test_manifestation_default_size(self):
        """
        If there is a manifesation on this node, then the
        corresponding dataset has a desired state of ``MOUNTED``.
        """
        expected_size = int(GiB(100).to_Byte().value)
        assert_desired_datasets(
            self, self.deployer,
            desired_manifestations=[
                ScenarioMixin.MANIFESTATION.transform(
                    ["dataset", "maximum_size"], lambda _: None
                ),
            ],
            expected_datasets=[
                DesiredDataset(
                    state=DatasetStates.MOUNTED,
                    dataset_id=ScenarioMixin.DATASET_ID,
                    metadata=ScenarioMixin.METADATA,
                    maximum_size=expected_size,
                    mount_point=self.deployer.mountroot.child(
                        unicode(ScenarioMixin.DATASET_ID)
                    ),
                ),
            ],
        )

    def test_deleted_manifestation(self):
        """
        If there is a mounted dataset that is deleted on this
        node, the corresponding dataset has a desired state of
        ``DELETED``.
        """
        assert_desired_datasets(
            self, self.deployer,
            desired_manifestations=[
                ScenarioMixin.MANIFESTATION.transform(
                    ["dataset", "deleted"], True,
                ),
            ],
            # XXX FLOC-1772 We only need to do this to handle
            # deleting unmounted datasets
            local_datasets=[
                DiscoveredDataset(
                    dataset_id=ScenarioMixin.DATASET_ID,
                    blockdevice_id=ScenarioMixin.BLOCKDEVICE_ID,
                    state=DatasetStates.MOUNTED,
                    maximum_size=REALISTIC_BLOCKDEVICE_SIZE,
                    device_path=FilePath('/dev/xvdf'),
                    mount_point=FilePath('/mount/path'),
                ),
            ],
            expected_datasets=[
                DesiredDataset(
                    state=DatasetStates.DELETED,
                    dataset_id=ScenarioMixin.DATASET_ID,
                    metadata=ScenarioMixin.METADATA,
                ),
            ],
        )

    def test_deleted_attached_manifest_dataset(self):
        """
        If there is a non-manifest dataset that is deleted on this
        node, the corresponding dataset has a desired state of
        ``MOUNTED``.

        This is only necessary until we can delete non-manifest datasets
        (FLOC-1772).
        """
        assert_desired_datasets(
            self, self.deployer,
            desired_manifestations=[
                ScenarioMixin.MANIFESTATION.transform(
                    ["dataset"], lambda d: d.set(deleted=True)
                ),
            ],
            # XXX FLOC-1772 We only need to do this to handle
            # deleting unmounted datasets
            local_datasets=[
                DiscoveredDataset(
                    dataset_id=ScenarioMixin.DATASET_ID,
                    blockdevice_id=ScenarioMixin.BLOCKDEVICE_ID,
                    state=DatasetStates.ATTACHED,
                    maximum_size=REALISTIC_BLOCKDEVICE_SIZE,
                    device_path=FilePath('/dev/xvdf'),
                ),
            ],
            expected_datasets=[
                DesiredDataset(
                    state=DatasetStates.MOUNTED,
                    dataset_id=ScenarioMixin.DATASET_ID,
                    metadata=ScenarioMixin.METADATA,
                    maximum_size=REALISTIC_BLOCKDEVICE_SIZE,
                    mount_point=self.deployer.mountroot.child(
                        unicode(ScenarioMixin.DATASET_ID)
                    ),
                ),
            ],
        )

    def test_deleted_non_manifest_dataset(self):
        """
        If there is a manfestation on this node that is deleted,
        the corresponding dataset has a desired state of ``MOUNTED``.

        This is only necessary until we can delete non-manifest datasets
        (FLOC-1772).
        """
        assert_desired_datasets(
            self, self.deployer,
            desired_manifestations=[
                ScenarioMixin.MANIFESTATION.transform(
                    ["dataset"], lambda d: d.set(deleted=True)
                ),
            ],
            # XXX FLOC-1772 We only need to do this to handle
            # deleting unmounted datasets
            local_datasets=[
                DiscoveredDataset(
                    dataset_id=ScenarioMixin.DATASET_ID,
                    blockdevice_id=ScenarioMixin.BLOCKDEVICE_ID,
                    state=DatasetStates.NON_MANIFEST,
                    maximum_size=REALISTIC_BLOCKDEVICE_SIZE,
                ),
            ],
            expected_datasets=[
                DesiredDataset(
                    state=DatasetStates.MOUNTED,
                    dataset_id=ScenarioMixin.DATASET_ID,
                    metadata=ScenarioMixin.METADATA,
                    maximum_size=REALISTIC_BLOCKDEVICE_SIZE,
                    mount_point=self.deployer.mountroot.child(
                        unicode(ScenarioMixin.DATASET_ID)
                    ),
                ),
            ],
        )

    def test_leased_mounted_manifestaion(self):
        """
        If there is a lease for a mounted dataset present on node,
        there is a corresponding dataset that has a desired state of
        ``MOUNTED``.
        """
        assert_desired_datasets(
            self, self.deployer,
            desired_manifestations=[],
            local_datasets=[
                DiscoveredDataset(
                    dataset_id=ScenarioMixin.DATASET_ID,
                    blockdevice_id=ScenarioMixin.BLOCKDEVICE_ID,
                    state=DatasetStates.MOUNTED,
                    maximum_size=REALISTIC_BLOCKDEVICE_SIZE,
                    device_path=FilePath('/dev/xvdf'),
                    mount_point=FilePath('/mount/path'),
                )
            ],
            expected_datasets=[
                DesiredDataset(
                    state=DatasetStates.MOUNTED,
                    dataset_id=ScenarioMixin.DATASET_ID,
                    maximum_size=REALISTIC_BLOCKDEVICE_SIZE,
                    metadata={},
                    mount_point=self.deployer.mountroot.child(
                        unicode(ScenarioMixin.DATASET_ID)
                    ),
                ),
            ],
            leases=Leases().acquire(
                now=datetime.now(tz=UTC),
                dataset_id=ScenarioMixin.DATASET_ID,
                node_id=self.deployer.node_uuid,
            )
        )

    def test_leased_attached_manifestaion(self):
        """
        If there is a lease for an attached dataset present on node,
        there is not a corresponding desired dataset.
        """
        assert_desired_datasets(
            self, self.deployer,
            desired_manifestations=[],
            local_datasets=[
                DiscoveredDataset(
                    dataset_id=ScenarioMixin.DATASET_ID,
                    blockdevice_id=ScenarioMixin.BLOCKDEVICE_ID,
                    state=DatasetStates.ATTACHED,
                    maximum_size=REALISTIC_BLOCKDEVICE_SIZE,
                    device_path=FilePath('/dev/xvdf'),
                )
            ],
            expected_datasets=[],
            leases=Leases().acquire(
                now=datetime.now(tz=UTC),
                dataset_id=ScenarioMixin.DATASET_ID,
                node_id=self.deployer.node_uuid,
            )
        )

    def test_leased_non_manifest(self):
        """
        If there is a lease for a mounted dataset present on node,
        there is a corresponding dataset that has a desired state of
        ``MOUNTED``.
        """
        assert_desired_datasets(
            self, self.deployer,
            desired_manifestations=[],
            local_datasets=[
                DiscoveredDataset(
                    dataset_id=ScenarioMixin.DATASET_ID,
                    blockdevice_id=ScenarioMixin.BLOCKDEVICE_ID,
                    state=DatasetStates.NON_MANIFEST,
                    maximum_size=REALISTIC_BLOCKDEVICE_SIZE,
                )
            ],
            expected_datasets=[],
            leases=Leases().acquire(
                now=datetime.now(tz=UTC),
                dataset_id=ScenarioMixin.DATASET_ID,
                node_id=self.deployer.node_uuid,
            )
        )

    def test_lease_elsewhere(self):
        """
        If there is a lease for a dataset on another node,
        there isn't a corresponding dataset that has a desired state
        of ``MOUNTED``.
        """
        assert_desired_datasets(
            self, self.deployer,
            local_datasets=[
                DiscoveredDataset(
                    dataset_id=ScenarioMixin.DATASET_ID,
                    blockdevice_id=ScenarioMixin.BLOCKDEVICE_ID,
                    state=DatasetStates.MOUNTED,
                    maximum_size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE,
                    device_path=FilePath('/dev/xvdf'),
                    mount_point=FilePath('/mount/path'),
                )
            ],
            expected_datasets=[],
            leases=Leases().acquire(
                now=datetime.now(tz=UTC),
                dataset_id=ScenarioMixin.DATASET_ID,
                node_id=uuid4(),
            )
        )

    def test_application_mounted_manifestaion(self):
        """
        If there is an application with attached volume, there is a
        corresponding dataset that has a desired state of
        ``MOUNTED``.
        """
        assert_desired_datasets(
            self, self.deployer,
            desired_manifestations=[],
            local_datasets=[
                DiscoveredDataset(
                    dataset_id=ScenarioMixin.DATASET_ID,
                    blockdevice_id=ScenarioMixin.BLOCKDEVICE_ID,
                    state=DatasetStates.MOUNTED,
                    maximum_size=REALISTIC_BLOCKDEVICE_SIZE,
                    device_path=FilePath('/dev/xvdf'),
                    mount_point=FilePath('/mount/path'),
                )
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
                DesiredDataset(
                    state=DatasetStates.MOUNTED,
                    dataset_id=ScenarioMixin.DATASET_ID,
                    metadata={},
                    maximum_size=REALISTIC_BLOCKDEVICE_SIZE,
                    mount_point=self.deployer.mountroot.child(
                        unicode(ScenarioMixin.DATASET_ID)),
                ),
            ],
        )

    def test_leased_manifestation(self):
        """
        If there is a manifesation on this node and lease for the
        corresponding volume for this node, then the corresponding
        dataset has a desired state of ``MOUNTED`` and the
        associated size corresponds to the discovered dataset.
        """
        assert_desired_datasets(
            self, self.deployer,
            desired_manifestations=[ScenarioMixin.MANIFESTATION],
            local_datasets=[
                DiscoveredDataset(
                    dataset_id=ScenarioMixin.DATASET_ID,
                    blockdevice_id=ScenarioMixin.BLOCKDEVICE_ID,
                    state=DatasetStates.MOUNTED,
                    maximum_size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE,
                    device_path=FilePath('/dev/xvdf'),
                    mount_point=FilePath('/mount/path'),
                )
            ],
            expected_datasets=[
                DesiredDataset(
                    state=DatasetStates.MOUNTED,
                    dataset_id=ScenarioMixin.DATASET_ID,
                    maximum_size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE,
                    mount_point=self.deployer.mountroot.child(
                        unicode(ScenarioMixin.DATASET_ID)),
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
        If there is a manfestation on this node that is deleted and
        there is a lease on the volume for this node, the
        corresponding dataset has a desired state of ``DELETED``.
        """
        assert_desired_datasets(
            self, self.deployer,
            desired_manifestations=[
                ScenarioMixin.MANIFESTATION.transform(
                    ["dataset"], lambda d: d.set(deleted=True)
                ),
            ],
            local_datasets=[
                DiscoveredDataset(
                    dataset_id=ScenarioMixin.DATASET_ID,
                    blockdevice_id=ScenarioMixin.BLOCKDEVICE_ID,
                    state=DatasetStates.MOUNTED,
                    maximum_size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE,
                    device_path=FilePath('/dev/xvdf'),
                    mount_point=FilePath('/mount/path'),
                )
            ],
            expected_datasets=[
                DesiredDataset(
                    state=DatasetStates.MOUNTED,
                    dataset_id=ScenarioMixin.DATASET_ID,
                    maximum_size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE,
                    mount_point=self.deployer.mountroot.child(
                        unicode(ScenarioMixin.DATASET_ID)),
                ),
            ],
            leases=Leases().acquire(
                now=datetime.now(tz=UTC),
                dataset_id=ScenarioMixin.DATASET_ID,
                node_id=self.deployer.node_uuid,
            )
        )


def assert_calculated_changes(
    case,
    discovered_datasets,
    desired_datasets,
    expected_changes,
):
    """
    Assert that ``BlockDeviceCalculater`` calculates certain changes
    in a certain circumstance.

    :param TestCase test_case: The ``TestCase`` which is being run.
    :param discovered_datasets: The current state of datasets on the
        node.
    :type discovered_datasets: iterable of `DiscoveredDataset``s
    :param desired_datasets: The desired state of datasets on the
        node.
    :type desired_datasets: iterable of ``DesiredDataset``s
    :param IStateChange expected_changes: The next changes to
        converge the state.

    :raise: A test failure exception if the manifestations are not what is
        expected.
    """
    calculater = BlockDeviceCalculater()
    changes = calculater.calculate_changes_for_datasets(
        discovered_datasets={dataset.dataset_id: dataset
                             for dataset in discovered_datasets},
        desired_datasets={dataset.dataset_id: dataset
                          for dataset in desired_datasets},
    )
    case.assertEqual(expected_changes, changes)


class BlockDeviceCalculaterTests(SynchronousTestCase):
    """
    Tests for ``BlockDeviceCalculater``.
    """

    # XXX It would be nice if there were some way to assert that these tests
    # are exhaustive.  It seems like this logic should be abstracted somehow.

    def test_NON_EXISTENT_MOUNTED_creates_volume(self):
        """
        If a volume doesn't exist and the desired state is ``MOUNTED``, then
        the expected change is to create the volume.
        """
        dataset_id = uuid4()
        assert_calculated_changes(
            self,
            discovered_datasets=[],
            desired_datasets=[
                DesiredDataset(
                    state=DatasetStates.MOUNTED,
                    dataset_id=dataset_id,
                    maximum_size=REALISTIC_BLOCKDEVICE_SIZE,
                    mount_point=FilePath("/mount/point"),
                ),
            ],
            expected_changes=in_parallel([
                CreateBlockDeviceDataset(
                    dataset=Dataset(
                        dataset_id=dataset_id,
                        maximum_size=REALISTIC_BLOCKDEVICE_SIZE,
                    ),
                    mountpoint=FilePath("/mount/point"),
                ),
            ])
        )

    def test_ATTACHED_ELSEWHERE_MOUNTED_does_nothing(self):
        """
        If a volume is currently ``ATTACHED_ELSEWHERE`` and the
        desired state is ``MOUNTED``, then the expected change is a
        noop.
        """
        dataset_id = uuid4()
        assert_calculated_changes(
            self,
            discovered_datasets=[
                DiscoveredDataset(
                    state=DatasetStates.ATTACHED_ELSEWHERE,
                    dataset_id=dataset_id,
                    blockdevice_id=ARBITRARY_BLOCKDEVICE_ID,
                    maximum_size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE,
                ),
            ],
            desired_datasets=[
                DesiredDataset(
                    state=DatasetStates.MOUNTED,
                    dataset_id=dataset_id,
                    maximum_size=REALISTIC_BLOCKDEVICE_SIZE,
                    mount_point=FilePath("/mount/point"),
                ),
            ],
            expected_changes=NoOp(),
        )

    def test_NON_MANIFEST_MOUNTED_attaches(self):
        """
        If a volume is currently ``NON_MANIFEST`` and the desired state is
        ``MOUNTED``, then the expected change is to attach the volume.
        """
        dataset_id = uuid4()
        assert_calculated_changes(
            self,
            discovered_datasets=[
                DiscoveredDataset(
                    state=DatasetStates.NON_MANIFEST,
                    dataset_id=dataset_id,
                    blockdevice_id=ARBITRARY_BLOCKDEVICE_ID,
                    maximum_size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE,
                ),
            ],
            desired_datasets=[
                DesiredDataset(
                    state=DatasetStates.MOUNTED,
                    dataset_id=dataset_id,
                    maximum_size=REALISTIC_BLOCKDEVICE_SIZE,
                    mount_point=FilePath("/"),
                ),
            ],
            expected_changes=in_parallel([

                AttachVolume(
                    dataset_id=dataset_id,
                    blockdevice_id=ARBITRARY_BLOCKDEVICE_ID,
                ),
            ])
        )

    def test_ATTACHED_MOUNTED_mounts(self):
        """
        If a volume is currently ``ATTACHED`` and the desired state is
        ``MOUNTED``, then the expected change is to mount the volume.
        """
        dataset_id = uuid4()
        assert_calculated_changes(
            self,
            discovered_datasets=[
                DiscoveredDataset(
                    state=DatasetStates.ATTACHED,
                    dataset_id=dataset_id,
                    blockdevice_id=ARBITRARY_BLOCKDEVICE_ID,
                    maximum_size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE,
                    device_path=FilePath('/dev/xvdf'),
                ),
            ],
            desired_datasets=[
                DesiredDataset(
                    state=DatasetStates.MOUNTED,
                    dataset_id=dataset_id,
                    maximum_size=REALISTIC_BLOCKDEVICE_SIZE,
                    mount_point=FilePath("/mount/point"),
                ),
            ],
            expected_changes=in_parallel([
                MountBlockDevice(
                    dataset_id=dataset_id,
                    blockdevice_id=ARBITRARY_BLOCKDEVICE_ID,
                    mountpoint=FilePath("/mount/point"),
                ),
            ])
        )

    def test_MOUNTED_MOUNTED_does_nothing(self):
        """
        If a volume is currently ``MOUNTED`` and the desired state is
        ``MOUNTED``, then the expected change is to do nothing.
        """
        dataset_id = uuid4()
        assert_calculated_changes(
            self,
            discovered_datasets=[
                DiscoveredDataset(
                    state=DatasetStates.MOUNTED,
                    dataset_id=dataset_id,
                    blockdevice_id=ARBITRARY_BLOCKDEVICE_ID,
                    maximum_size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE,
                    device_path=FilePath('/dev/xvdf'),
                    mount_point=FilePath("/mount/point"),
                ),
            ],
            desired_datasets=[
                DesiredDataset(
                    state=DatasetStates.MOUNTED,
                    dataset_id=dataset_id,
                    maximum_size=REALISTIC_BLOCKDEVICE_SIZE,
                    mount_point=FilePath("/mount/point"),
                ),
            ],
            expected_changes=NoOp(),
        )

    def test_NON_EXISTENT_NON_MANIFEST_does_nothing(self):
        """
        If a volume doesn't exist and the desired state is ``NON_MANIFEST``,
        then the expected change is to do nothing.

        Note: we don't have any way to pick which node should create a volume.
        """
        dataset_id = uuid4()
        assert_calculated_changes(
            self,
            discovered_datasets=[],
            desired_datasets=[
                DesiredDataset(
                    state=DatasetStates.NON_MANIFEST,
                    dataset_id=dataset_id,
                    maximum_size=REALISTIC_BLOCKDEVICE_SIZE,
                ),
            ],
            expected_changes=NoOp(),
        )

    def test_NON_MANIFEST_NON_MANIFEST_does_nothing(self):
        """
        If a volume is currently ``NON_MANIFEST`` and the desired state is
        ``NON_MANIFEST``, then the expected change is to do nothing.
        """
        dataset_id = uuid4()
        assert_calculated_changes(
            self,
            discovered_datasets=[
                DiscoveredDataset(
                    state=DatasetStates.NON_MANIFEST,
                    dataset_id=dataset_id,
                    blockdevice_id=ARBITRARY_BLOCKDEVICE_ID,
                    maximum_size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE,
                ),
            ],
            desired_datasets=[
                DesiredDataset(
                    state=DatasetStates.NON_MANIFEST,
                    dataset_id=dataset_id,
                    maximum_size=REALISTIC_BLOCKDEVICE_SIZE,
                ),
            ],
            expected_changes=NoOp()
        )

    def test_ATTACHED_NON_MANIFEST_detaches(self):
        """
        If a volume is currently ``ATTACHED`` and the desired state is
        ``NON_MANIFEST``, then the expected change is to detach the volume.
        """
        dataset_id = uuid4()
        assert_calculated_changes(
            self,
            discovered_datasets=[
                DiscoveredDataset(
                    state=DatasetStates.ATTACHED,
                    dataset_id=dataset_id,
                    blockdevice_id=ARBITRARY_BLOCKDEVICE_ID,
                    maximum_size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE,
                    device_path=FilePath('/dev/xvdf'),
                ),
            ],
            desired_datasets=[
                DesiredDataset(
                    state=DatasetStates.NON_MANIFEST,
                    dataset_id=dataset_id,
                    maximum_size=REALISTIC_BLOCKDEVICE_SIZE,
                ),
            ],
            expected_changes=in_parallel([
                DetachVolume(
                    dataset_id=dataset_id,
                    blockdevice_id=ARBITRARY_BLOCKDEVICE_ID,
                ),
            ])
        )

    def test_MOUNTED_NON_MANIFEST_unmounts(self):
        """
        If a volume is currently ``MOUNTED`` and the desired state is
        ``NON_MANIFEST``, then the expected change is to unmount the volume.
        """
        dataset_id = uuid4()
        assert_calculated_changes(
            self,
            discovered_datasets=[
                DiscoveredDataset(
                    state=DatasetStates.MOUNTED,
                    dataset_id=dataset_id,
                    blockdevice_id=ARBITRARY_BLOCKDEVICE_ID,
                    maximum_size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE,
                    device_path=FilePath('/dev/xvdf'),
                    mount_point=FilePath("/mount/point"),
                ),
            ],
            desired_datasets=[
                DesiredDataset(
                    state=DatasetStates.NON_MANIFEST,
                    dataset_id=dataset_id,
                    maximum_size=REALISTIC_BLOCKDEVICE_SIZE,
                ),
            ],
            expected_changes=in_parallel([
                UnmountBlockDevice(
                    dataset_id=dataset_id,
                    blockdevice_id=ARBITRARY_BLOCKDEVICE_ID,
                )
            ]),
        )

    def test_NON_EXISTENT_DELETED_does_nothing(self):
        """
        If a volume doesn't exist and the desired state is ``DELETED``,
        then the expected change is to do nothing.
        """
        dataset_id = uuid4()
        assert_calculated_changes(
            self,
            discovered_datasets=[],
            desired_datasets=[
                DesiredDataset(
                    state=DatasetStates.NON_MANIFEST,
                    dataset_id=dataset_id,
                    maximum_size=REALISTIC_BLOCKDEVICE_SIZE,
                ),
            ],
            expected_changes=NoOp(),
        )

    def test_ATTACHED_ELSEWHERE_DELETED_does_nothing(self):
        """
        If a volume is attached elsewhere and the desired state is
        ``DELETED``, then the expected change is to do nothing.
        """
        dataset_id = uuid4()
        assert_calculated_changes(
            self,
            discovered_datasets=[],
            desired_datasets=[
                DesiredDataset(
                    state=DatasetStates.NON_MANIFEST,
                    dataset_id=dataset_id,
                    maximum_size=REALISTIC_BLOCKDEVICE_SIZE,
                ),
            ],
            expected_changes=NoOp(),
        )

    def test_NON_MANIFEST_DELETED_does_nothing(self):
        """
        If a volume is currently ``NON_MANIFEST`` and the desired state is
        ``DELETED``, then the expected change is to do nothing.
        """
        dataset_id = uuid4()
        assert_calculated_changes(
            self,
            discovered_datasets=[
                DiscoveredDataset(
                    state=DatasetStates.NON_MANIFEST,
                    dataset_id=dataset_id,
                    blockdevice_id=ARBITRARY_BLOCKDEVICE_ID,
                    maximum_size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE,
                ),
            ],
            desired_datasets=[
                DesiredDataset(
                    state=DatasetStates.DELETED,
                    dataset_id=dataset_id,
                ),
            ],
            expected_changes=NoOp(),
        )

    def test_ATTACHED_DELETED_detaches(self):
        """
        If a volume is currently ``ATTACHED`` and the desired state is
        ``DELETED``, then the expected change is detach.
        """
        dataset_id = uuid4()
        assert_calculated_changes(
            self,
            discovered_datasets=[
                DiscoveredDataset(
                    state=DatasetStates.ATTACHED,
                    dataset_id=dataset_id,
                    blockdevice_id=ARBITRARY_BLOCKDEVICE_ID,
                    maximum_size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE,
                    device_path=FilePath('/dev/xvdf'),
                ),
            ],
            desired_datasets=[
                DesiredDataset(
                    state=DatasetStates.DELETED,
                    dataset_id=dataset_id,
                ),
            ],
            expected_changes=in_parallel([
                DetachVolume(
                    dataset_id=dataset_id,
                    blockdevice_id=ARBITRARY_BLOCKDEVICE_ID,
                ),
            ]),
        )

    def test_MOUNTED_DELETED_destroys(self):
        """
        If a volume is currently ``MOUNTED`` and the desired state is
        ``DELETED``, then the expected change is to destroy the volume.
        """
        dataset_id = uuid4()
        assert_calculated_changes(
            self,
            discovered_datasets=[
                DiscoveredDataset(
                    state=DatasetStates.MOUNTED,
                    dataset_id=dataset_id,
                    blockdevice_id=ARBITRARY_BLOCKDEVICE_ID,
                    maximum_size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE,
                    device_path=FilePath('/dev/xvdf'),
                    mount_point=FilePath("/mount/point"),
                ),
            ],
            desired_datasets=[
                DesiredDataset(
                    state=DatasetStates.DELETED,
                    dataset_id=dataset_id,
                ),
            ],
            expected_changes=in_parallel([
                DestroyBlockDeviceDataset(
                    dataset_id=dataset_id,
                    blockdevice_id=ARBITRARY_BLOCKDEVICE_ID,
                )
            ]),
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
            calculater=RecordingCalculater(self.expected_change),
        )
        self.local_state = BlockDeviceDeployerLocalState(
            node_uuid=ScenarioMixin.NODE_UUID,
            hostname=ScenarioMixin.NODE,
            datasets={},
            volumes={},
        )

    def test_calculates_changes(self):
        """
        ``BlockDeviceDeployer.calculate_changes`` returns the changes
        calculated by calling the provided ``ICalculater``.
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
            additional_node_states=set(),
            additional_node_config=set(),
            expected_changes=self.expected_change,
            local_state=self.local_state,
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


def umount(device_file):
    """
    Unmount a filesystem.

    :param FilePath device_file: The device file that is mounted.
    """
    check_output(['umount', device_file.path])


def umount_all(root_path):
    """
    Unmount all devices with mount points contained in ``root_path``.

    :param FilePath root_path: A directory in which to search for mount points.
    """
    for partition in psutil.disk_partitions():
        try:
            FilePath(partition.mountpoint).segmentsFrom(root_path)
        except ValueError:
            pass
        else:
            umount(FilePath(partition.device))


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
    size=REALISTIC_BLOCKDEVICE_SIZE,
    dataset_id=uuid4(),
)


def _make_destroy_dataset():
    """
    Make a ``DestroyBlockDeviceDataset`` instance for
    ``make_istate_tests``.
    """
    return DestroyBlockDeviceDataset(
        dataset_id=_ARBITRARY_VOLUME.dataset_id,
        blockdevice_id=_ARBITRARY_VOLUME.blockdevice_id
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


class DestroyBlockDeviceDatasetInitTests(
    make_with_init_tests(
        DestroyBlockDeviceDataset,
        dict(dataset_id=uuid4(), blockdevice_id=ARBITRARY_BLOCKDEVICE_ID),
        dict(),
    )
):
    """
    Tests for ``DestroyBlockDeviceDataset`` initialization.
    """


class DestroyBlockDeviceDatasetTests(
    make_istatechange_tests(
        DestroyBlockDeviceDataset,
        # Avoid using the same instance, just provide the same value.
        lambda _uuid=uuid4(): dict(dataset_id=_uuid,
                                   blockdevice_id=ARBITRARY_BLOCKDEVICE_ID),
        lambda _uuid=uuid4(): dict(dataset_id=_uuid,
                                   blockdevice_id=ARBITRARY_BLOCKDEVICE_ID_2),
    )
):
    """
    Tests for ``DestroyBlockDeviceDataset``.
    """
    def test_dataset_id_must_be_uuid(self):
        """
        If the value given for ``dataset_id`` is not an instance of ``UUID``
        when initializing ``DestroyBlockDeviceDataset``, ``TypeError`` is
        raised.
        """
        self.assertRaises(
            TypeError, DestroyBlockDeviceDataset, dataset_id=object(),
            blockdevice_id=ARBITRARY_BLOCKDEVICE_ID
        )

    @capture_logging(multistep_change_log(
        LOG_SEQUENTIALLY,
        [UNMOUNT_BLOCK_DEVICE, DETACH_VOLUME, DESTROY_VOLUME]
    ))
    def test_run(self, logger):
        """
        After running ``DestroyBlockDeviceDataset``, its volume has been
        unmounted, detached, and destroyed.
        """
        self.patch(blockdevice, "_logger", logger)

        node = u"192.0.2.3"
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
        mount(device, mountpoint)

        change = DestroyBlockDeviceDataset(
            dataset_id=dataset_id, blockdevice_id=volume.blockdevice_id)
        self.successResultOf(run_state_change(change, deployer))

        # It's only possible to destroy a volume that's been detached.  It's
        # only possible to detach a volume that's been unmounted.  If the
        # volume doesn't exist, all three things we wanted to happen have
        # happened.
        self.assertEqual([], api.list_volumes())


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


class _MountScenario(PRecord):
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
            dataset=Dataset(dataset_id=unicode(uuid4())),
            mountpoint=FilePath(b"/foo"),
        ),
        dict(),
    )
):
    """
    Tests for ``CreateBlockDeviceDataset`` initialization.
    """


class CreateBlockDeviceDatasetInterfaceTests(
    make_istatechange_tests(
        CreateBlockDeviceDataset,
        lambda _uuid=uuid4(): dict(
            dataset=Dataset(dataset_id=unicode(_uuid)),
            mountpoint=FilePath(b"/foo"),
        ),
        lambda _uuid=uuid4(): dict(
            dataset=Dataset(dataset_id=unicode(_uuid)),
            mountpoint=FilePath(b"/bar"),
        ),
    )
):
    """
    ``CreateBlockDeviceDataset`` interface adherance tests.
    """


class MountedVolumeInfo(PClass):
    """
    A utility class for information about a volume and its mountpoint.

    :ivar BlockDeviceVolume volume: The volume.
    :ivar FilePath device_path: The path to the device.
    :ivar FilePath expected_mountpoint: The expected location for the volume
        mount.
    :ivar unicode compute_instance_id: The instance of the compute node that it
        is mounted on.
    """
    volume = field(type=BlockDeviceVolume)
    device_path = field(type=FilePath)
    expected_mountpoint = field(type=FilePath)
    compute_instance_id = field(type=unicode)


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

        :returns: A ``MountedVolumeInfo`` for the created volume.
        """
        expected_mountpoint = self.mountroot.child(
            unicode(dataset_id).encode("ascii")
        )

        dataset = Dataset(
            dataset_id=unicode(dataset_id),
            maximum_size=maximum_size,
            metadata=metadata
        )

        change = CreateBlockDeviceDataset(
            dataset=dataset, mountpoint=expected_mountpoint
        )

        run_state_change(change, self.deployer)

        [volume] = self.api.list_volumes()
        device_path = self.api.get_device_path(volume.blockdevice_id)
        return MountedVolumeInfo(
            volume=volume,
            device_path=device_path,
            expected_mountpoint=expected_mountpoint,
            compute_instance_id=self.api.compute_instance_id()
        )


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

        dataset = Dataset(
            dataset_id=unicode(dataset_id),
            maximum_size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE
        )

        change = CreateBlockDeviceDataset(
            dataset=dataset,
            mountpoint=self.mountroot.child(
                unicode(dataset_id).encode("ascii")
            )
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
        volume_info = self._create_blockdevice_dataset(
            dataset_id=dataset_id,
            maximum_size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE,
        )

        expected_volume = _blockdevicevolume_from_dataset_id(
            dataset_id=dataset_id, attached_to=volume_info.compute_instance_id,
            size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE,
        )

        self.assertEqual(expected_volume, volume_info.volume)

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
        volume_info = self._create_blockdevice_dataset(
            dataset_id=dataset_id,
            maximum_size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE,
            metadata={PROFILE_METADATA_KEY: u"gold"}
        )

        expected_volume = _blockdevicevolume_from_dataset_id(
            dataset_id=dataset_id, attached_to=volume_info.compute_instance_id,
            size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE,
        )

        self.assertEqual(expected_volume, volume_info.volume)

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
            dataset_id=dataset_id, attached_to=volume_info.compute_instance_id,
            size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE + LOOPBACK_ALLOCATION_UNIT,
        )
        self.assertEqual(expected_volume, volume_info.volume)

    def test_run_mkfs_and_mount(self):
        """
        ``CreateBlockDeviceDataset.run`` initializes the attached block device
        with an ext4 filesystem and mounts it.
        """
        dataset_id = uuid4()
        volume_info = self._create_blockdevice_dataset(
            dataset_id=dataset_id,
            maximum_size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE,
        )

        self.assertIn(
            (volume_info.device_path.path,
             volume_info.expected_mountpoint.path,
             b"ext4"),
            list(
                (partition.device, partition.mountpoint, partition.fstype)
                for partition
                in psutil.disk_partitions()
            )
        )

    def test_mountpoint_permissions(self):
        """
        The mountpoint is world-writeable (since containers can run as any
        user), and its parent is only accessible as current user (for
        security).
        """
        mountpoint = self._create_blockdevice_dataset(
            uuid4(), maximum_size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE
        ).expected_mountpoint
        mountroot = mountpoint.parent()
        self.assertEqual((mountroot.getPermissions().shorthand(),
                          mountpoint.getPermissions().shorthand()),
                         ('rwx------', 'rwxrwxrwx'))


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

        expected_volume = _blockdevicevolume_from_dataset_id(
            dataset_id=dataset_id, attached_to=volume_info.compute_instance_id,
            size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE,
        )

        self.assertEqual(expected_volume, volume_info.volume)
        self.assertEqual(
            profile,
            self.api.dataset_profiles[volume_info.volume.blockdevice_id])


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
    def test_run(self):
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
