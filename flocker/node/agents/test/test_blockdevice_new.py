# Copyright ClusterHQ Ltd.  See LICENSE file for details.

"""
Tests for ``flocker.node.agents.blockdevice``.
"""

# XXX New file for rewrite.

from uuid import uuid4
from os import getuid
from subprocess import check_output
import time

from bitmath import MiB

import psutil

from zope.interface.verify import verifyObject

from twisted.python.runtime import platform
from twisted.python.filepath import FilePath
from twisted.trial.unittest import SynchronousTestCase, SkipTest

from eliot import start_action, write_traceback, Message
from eliot.testing import (
    capture_logging,
    assertHasMessage,
)

from ....testtools import (
    random_name,
    run_process,
)
from ....control import (
    NodeState,
    NonManifestDatasets,
    Dataset,
    Manifestation,
)

from ... import ILocalState
from .. import blockdevice
from ..blockdevice import (
    BlockDeviceDeployerLocalState,
    BlockDeviceDeployer,
    _SyncToThreadedAsyncAPIAdapter,
    DatasetStates, DiscoveredDataset,
    INVALID_DEVICE_PATH,
)
from ..loopback import (
    # check_allocatable_size,
    LoopbackBlockDeviceAPI,
    # _losetup_list_parse,
    # _losetup_list, _blockdevicevolume_from_dataset_id,
    # _backing_file_name,
)

from ...testtools import (
    ideployer_tests_factory,
)
# Move these somewhere else, write tests for them. FLOC-1774
from ....common.test.test_thread import NonThreadPool, NonReactor


CLEANUP_RETRY_LIMIT = 10
# Enough space for the ext4 journal:
LOOPBACK_MINIMUM_ALLOCATABLE_SIZE = int(MiB(16).to_Byte().value)

ARBITRARY_BLOCKDEVICE_ID = u'blockdevice_id_1'

if not platform.isLinux():
    # The majority of Flocker isn't supported except on Linux - this test
    # module just happens to run some code that obviously breaks on some other
    # platforms.  Rather than skipping each test module individually it would
    # be nice to have some single global solution.  FLOC-1560, FLOC-1205
    skip = "flocker.node.agents.blockdevice is only supported on Linux"


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
                    write_traceback()

            time.sleep(1.0)
            volumes = api.list_volumes()
            retry += 1

        if len(volumes) > 0:
            Message.new(u"agent:blockdevice:failedcleanup:volumes",
                        volumes=volumes).write()


def mount(device, mountpoint):
    """
    Synchronously mount a filesystem.

    :param FilePath device: The path to the device file containing the
        filesystem.
    :param mountpoint device: The path to an existing directory at which to
        mount the filesystem.
    """
    run_process([b"mount", device.path, mountpoint.path])


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


class BlockDeviceDeployerTests(
        ideployer_tests_factory(create_blockdevicedeployer)
):
    """
    Tests for ``IDeployer`` implementation of ``BlockDeviceDeployer``.
    """


def assert_discovered_state(
    case,
    deployer,
    expected_discoved_datasets,
    expected_volumes,
):
    """
    Assert that datasets on the state object returned by
    ``deployer.discover_state`` equals the given list of datasets.

    :param TestCase case: The running test.
    :param IDeployer deployer: The object to use to discover the state.
    :param list expected_manifestations: The ``Manifestation``\ s expected to
        be discovered on the deployer's node.
    :param expected_nonmanifest_datasets: Sequence of the ``Dataset``\ s
        expected to be discovered on the cluster but not attached to any
        node.
    :param expected_volumes: The expected sequence of ``BlockDeviceVolume``
        instances. discover_state() is expected to return an
        ``BlockDeviceDeployerLocalState`` with a volumes attribute equal to
        this.
    :param dict expected_devices: The OS device files which are expected to be
        discovered as allocated to volumes attached to the node.  See
        ``NodeState.devices``.

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
                for dataset in expected_discoved_datasets
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
        ``BlockDeviceDeployer._discover_raw_state``
        returns a ``RawState`` with the
        ``compute_instance_id`` that the ``api``
        reports.
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

    def test_attached_unmounted_device(self):
        """
        If a volume is attached but not mounted, it is included as a
        non-manifest dataset returned by ``BlockDeviceDeployer.discover_state``
        and not as a manifestation on the ``NodeState``.
        """
        unmounted = self.api.create_volume(
            dataset_id=uuid4(),
            size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE,
        )
        raw_state = self.deployer._discover_raw_state()
        self.assertEqual(raw_state.volumes, [
            unmounted,
        ])


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

    def test_created_volume(self):
        volume = self.api.create_volume(
            dataset_id=uuid4(),
            size=LOOPBACK_MINIMUM_ALLOCATABLE_SIZE,
        )
        assert_discovered_state(
            self, self.deployer,
            expected_discoved_datasets=[
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
        assert_discovered_state(
            self, self.deployer,
            expected_discoved_datasets=[
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
            expected_discoved_datasets=[
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
            expected_discoved_datasets=[
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
        # XXX This discovers volums as NON_MANIFEST, but we should
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
            expected_discoved_datasets=[
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


def assert_shared_state_changes(case,
                                deployer,
                                expected_manifestations,
                                expected_nonmanifest_datasets=(),
                                expected_volumes=[],
                                expected_devices={}):
    """
    Assert that the manifestations on the state object returned by
    ``deployer.discover_state`` equals the given list of manifestations.

    :param TestCase case: The running test.
    :param IDeployer deployer: The object to use to discover the state.
    :param list expected_manifestations: The ``Manifestation``\ s expected to
        be discovered on the deployer's node.
    :param expected_nonmanifest_datasets: Sequence of the ``Dataset``\ s
        expected to be discovered on the cluster but not attached to any
        node.
    :param expected_volumes: The expected sequence of ``BlockDeviceVolume``
        instances. discover_state() is expected to return an
        ``BlockDeviceDeployerLocalState`` with a volumes attribute equal to
        this.
    :param dict expected_devices: The OS device files which are expected to be
        discovered as allocated to volumes attached to the node.  See
        ``NodeState.devices``.

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
    node_state, nonmanifest_datasets = local_state.shared_state_changes()
    expected_paths = {}
    for manifestation in expected_manifestations:
        dataset_id = manifestation.dataset.dataset_id
        mountpath = deployer._mountpath_for_manifestation(manifestation)
        expected_paths[dataset_id] = mountpath
    case.assertEqual(NodeState(
        applications=None,
        uuid=deployer.node_uuid,
        hostname=deployer.hostname,
        manifestations={
            m.dataset_id: m for m in expected_manifestations},
        paths=expected_paths,
        devices=expected_devices,
    ), node_state
    )
    # FLOC-1806 - Make this actually be a dictionary (callers pass a list
    # instead) and construct the ``NonManifestDatasets`` with the
    # ``Dataset`` instances that are present as values.
    case.assertEqual(
        NonManifestDatasets(datasets={
            unicode(dataset_id):
            Dataset(dataset_id=unicode(dataset_id))
            for dataset_id in expected_nonmanifest_datasets
        }), nonmanifest_datasets)


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
        BlockDeviceDeployerLocalState`` and a
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
        When there is a a dataset in the ``NON_MANIFEST`` state,
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

    def test_attached_dataset(self):
        """
        When there is a a dataset in the ``ATTACHED`` state,
        it is reported as a non-manifest dataset.
        """
        dataset_id = uuid4()
        local_state = BlockDeviceDeployerLocalState(
            node_uuid=self.node_uuid,
            hostname=self.hostname,
            datasets={
                dataset_id: DiscoveredDataset(
                    state=DatasetStates.ATTACHED,
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

    def test_mounted_dataset(self):
        """
        When there is a a dataset in the ``MOUNTED`` state,
        it is reported as a non-manifest dataset.
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
