# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for ``flocker.node.agents.blockdevice``.
"""

import os
from uuid import UUID, uuid4
from subprocess import STDOUT, PIPE, Popen, check_output

import psutil

from zope.interface.verify import verifyObject

from pyrsistent import InvariantException

from twisted.python.runtime import platform
from twisted.python.filepath import FilePath
from twisted.trial.unittest import SynchronousTestCase, SkipTest

from eliot.testing import validate_logging, LoggedAction

from .. import blockdevice

from ..blockdevice import (
    BlockDeviceDeployer, LoopbackBlockDeviceAPI, IBlockDeviceAPI,
    BlockDeviceVolume, UnknownVolume, AlreadyAttachedVolume,
    CreateBlockDeviceDataset, UnattachedVolume,
    DestroyBlockDeviceDataset, UnmountBlockDevice, DetachVolume,
    DestroyVolume,
    _losetup_list_parse, _losetup_list, _blockdevicevolume_from_dataset_id,
    DESTROY_BLOCK_DEVICE_DATASET, UNMOUNT_BLOCK_DEVICE, DETACH_VOLUME,
    DESTROY_VOLUME,
)

from ... import IStateChange, in_parallel
from ...testtools import ideployer_tests_factory, to_node
from ....testtools import run_process
from ....control import (
    Dataset, Manifestation, Node, NodeState, Deployment, DeploymentState,
    NonManifestDatasets,
)

GIBIBYTE = 2 ** 30
REALISTIC_BLOCKDEVICE_SIZE = 4 * GIBIBYTE
LOOPBACK_BLOCKDEVICE_SIZE = 1024 * 1024 * 64

if not platform.isLinux():
    # The majority of Flocker isn't supported except on Linux - this test
    # module just happens to run some code that obviously breaks on some other
    # platforms.  Rather than skipping each test module individually it would
    # be nice to have some single global solution.  FLOC-1560, FLOC-1205
    skip = "flocker.node.agents.blockdevice is only supported on Linux"


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


class BlockDeviceDeployerTests(
        ideployer_tests_factory(
            lambda test: BlockDeviceDeployer(
                hostname=u"localhost",
                block_device_api=loopbackblockdeviceapi_for_test(test)
            )
        )
):
    """
    Tests for ``BlockDeviceDeployer``.
    """


class BlockDeviceDeployerDiscoverStateTests(SynchronousTestCase):
    """
    Tests for ``BlockDeviceDeployer.discover_state``.
    """
    def setUp(self):
        self.expected_hostname = u'192.0.2.123'
        self.api = loopbackblockdeviceapi_for_test(self)
        self.deployer = BlockDeviceDeployer(
            hostname=self.expected_hostname,
            block_device_api=self.api,
            mountroot=mountroot_for_test(self),
        )

    def assertDiscoveredState(self, deployer, expected_manifestations,
                              expected_nonmanifest_datasets=None):
        """
        Assert that the manifestations on the state object returned by
        ``deployer.discover_state`` equals the given list of manifestations.

        :param IDeployer deployer: The object to use to discover the state.
        :param list expected_manifestations: The ``Manifestation``\ s expected
            to be discovered.

        :raise: A test failure exception if the manifestations are not what is
                expected.
        """
        discovering = deployer.discover_state(
            NodeState(hostname=self.expected_hostname)
        )
        state = self.successResultOf(discovering)
        expected_paths = {}
        for manifestation in expected_manifestations:
            dataset_id = manifestation.dataset.dataset_id
            mountpath = deployer._mountpath_for_manifestation(manifestation)
            expected_paths[dataset_id] = mountpath
        expected = (
            NodeState(
                hostname=deployer.hostname,
                manifestations={
                    m.dataset_id: m for m in expected_manifestations},
                paths=expected_paths,
            ),
        )
        if expected_nonmanifest_datasets is not None:
            expected += (
                NonManifestDatasets(datasets={
                    unicode(dataset_id):
                    Dataset(dataset_id=unicode(dataset_id))
                    for dataset_id in expected_nonmanifest_datasets
                }),
            )
        self.assertEqual(expected, state)

    def test_no_devices(self):
        """
        ``BlockDeviceDeployer.discover_state`` returns a ``NodeState`` with
        empty ``manifestations`` if the ``api`` reports no locally attached
        volumes.
        """
        self.assertDiscoveredState(self.deployer, [])

    def test_attached_unmounted_device(self):
        """
        If a volume is attached but not mounted, it is included as a
        non-manifest dataset returned by ``BlockDeviceDeployer.discover_state``
        and not as a manifestation on the ``NodeState``.
        """
        unmounted = self.api.create_volume(
            dataset_id=uuid4(),
            size=REALISTIC_BLOCKDEVICE_SIZE,
        )
        self.api.attach_volume(
            unmounted.blockdevice_id, self.expected_hostname
        )
        self.assertDiscoveredState(
            self.deployer, expected_manifestations=[],
            expected_nonmanifest_datasets=[unmounted.dataset_id]
        )

    def test_attached_and_mismounted(self):
        """
        If a volume is attached and mounted but not mounted at the location
        ``BlockDeviceDeployer`` expects, it is included as a non-manifest
        dataset returned by ``BlockDeviceDeployer.discover_state`` and not as a
        manifestation on the ``NodeState``.
        """
        unexpected = self.api.create_volume(
            dataset_id=uuid4(),
            size=LOOPBACK_BLOCKDEVICE_SIZE,
        )

        self.api.attach_volume(
            unexpected.blockdevice_id, self.expected_hostname
        )

        device = self.api.get_device_path(unexpected.blockdevice_id)
        make_filesystem(device, block_device=True)

        # Mount it somewhere beneath the expected mountroot (so that it is
        # cleaned up automatically) but not at the expected place beneath it.
        mountpoint = self.deployer.mountroot.child(b"nonsense")
        mountpoint.makedirs()
        mount(device, mountpoint)

        self.assertDiscoveredState(
            self.deployer,
            expected_manifestations=[],
            expected_nonmanifest_datasets=[unexpected.dataset_id]
        )

    def test_unrelated_mounted(self):
        """
        If a volume is attached but an unrelated filesystem is mounted at the
        expected location for that volume, it is included as a non-manifest
        dataset returned by ``BlockDeviceDeployer.discover_state`` and not as a
        manifestation on the ``NodeState``.
        """
        unrelated_device = FilePath(self.mktemp())
        with unrelated_device.open("w") as unrelated_file:
            unrelated_file.truncate(LOOPBACK_BLOCKDEVICE_SIZE)

        unmounted = self.api.create_volume(
            dataset_id=uuid4(),
            size=REALISTIC_BLOCKDEVICE_SIZE,
        )
        mountpoint = self.deployer.mountroot.child(bytes(unmounted.dataset_id))
        mountpoint.makedirs()
        self.api.attach_volume(
            unmounted.blockdevice_id, self.expected_hostname
        )

        make_filesystem(unrelated_device, block_device=False)
        mount(unrelated_device, mountpoint)

        self.assertDiscoveredState(
            self.deployer,
            expected_manifestations=[],
            expected_nonmanifest_datasets=[unmounted.dataset_id]
        )

    def test_one_device(self):
        """
        ``BlockDeviceDeployer.discover_state`` returns a ``NodeState`` with one
        ``manifestations`` if the ``api`` reports one locally attached volume
        and the volume's filesystem is mounted in the right place.
        """
        dataset_id = uuid4()
        new_volume = self.api.create_volume(
            dataset_id=dataset_id,
            size=REALISTIC_BLOCKDEVICE_SIZE
        )
        self.api.attach_volume(
            new_volume.blockdevice_id, self.expected_hostname
        )
        device = self.api.get_device_path(new_volume.blockdevice_id)
        mountpoint = self.deployer.mountroot.child(bytes(dataset_id))
        mountpoint.makedirs()
        make_filesystem(device, block_device=True)
        mount(device, mountpoint)
        expected_dataset = Dataset(
            dataset_id=dataset_id,
            maximum_size=REALISTIC_BLOCKDEVICE_SIZE
        )
        expected_manifestation = Manifestation(
            dataset=expected_dataset, primary=True
        )
        self.assertDiscoveredState(self.deployer, [expected_manifestation])

    def test_only_remote_device(self):
        """
        ``BlockDeviceDeployer.discover_state`` does not consider remotely
        attached volumes.
        """
        dataset_id = uuid4()
        new_volume = self.api.create_volume(
            dataset_id=dataset_id,
            size=REALISTIC_BLOCKDEVICE_SIZE
        )
        self.api.attach_volume(new_volume.blockdevice_id, u'some.other.host')
        self.assertDiscoveredState(self.deployer, [])

    def test_only_unattached_devices(self):
        """
        ``BlockDeviceDeployer.discover_state`` discovers volumes that are not
        attached to any node and creates entries in a ``NonManifestDatasets``
        instance corresponding to them.
        """
        dataset_id = uuid4()
        self.api.create_volume(
            dataset_id=dataset_id,
            size=REALISTIC_BLOCKDEVICE_SIZE)
        self.assertDiscoveredState(
            self.deployer,
            expected_manifestations=[],
            expected_nonmanifest_datasets=[dataset_id]
        )


class BlockDeviceDeployerDestructionCalculateChangesTests(
        SynchronousTestCase
):
    """
    Tests for ``BlockDeviceDeployer.calculate_changes`` in the cases relating
    to dataset destruction.
    """
    DATASET_ID = uuid4()
    NODE = u"192.0.2.1"

    # The state of a single node which has a single primary manifestation for a
    # dataset.  Common starting point for several of the test scenarios.
    ONE_DATASET_STATE = NodeState(
        hostname=NODE,
        manifestations={
            unicode(DATASET_ID): Manifestation(
                dataset=Dataset(
                    dataset_id=unicode(DATASET_ID),
                ),
                primary=True,
            ),
        },
        paths={
            unicode(DATASET_ID):
            FilePath(b"/flocker/").child(bytes(DATASET_ID)),
        },
    )

    def test_undeleted_dataset_not_deleted(self):
        """
        ``BlockDeviceDeployer.calculate_changes`` does not calculate a change
        to destroy datasets that are not marked as deleted in the
        configuration.
        """
        local_state = self.ONE_DATASET_STATE
        local_config = to_node(local_state)

        cluster_state = DeploymentState(
            nodes={local_state}
        )

        cluster_configuration = Deployment(
            nodes={local_config}
        )

        api = loopbackblockdeviceapi_for_test(self)
        volume = api.create_volume(
            dataset_id=self.DATASET_ID, size=REALISTIC_BLOCKDEVICE_SIZE
        )
        api.attach_volume(volume.blockdevice_id, self.NODE)

        deployer = BlockDeviceDeployer(
            hostname=self.NODE,
            block_device_api=api,
        )

        changes = deployer.calculate_changes(
            cluster_configuration, cluster_state,
        )

        self.assertEqual(
            in_parallel(changes=[]),
            changes
        )

    def test_deleted_dataset_volume_exists(self):
        """
        If the configuration indicates a dataset with a primary manifestation
        on the node has been deleted and the volume associated with that
        dataset still exists, ``BlockDeviceDeployer.calculate_changes`` returns
        a ``DestroyBlockDeviceDataset`` state change operation.
        """
        local_state = self.ONE_DATASET_STATE
        cluster_state = Deployment(
            nodes={to_node(local_state)}
        )

        local_config = to_node(local_state).transform(
            ["manifestations", unicode(self.DATASET_ID), "dataset", "deleted"],
            True
        )
        cluster_configuration = Deployment(
            nodes={local_config}
        )

        api = loopbackblockdeviceapi_for_test(self)
        volume = api.create_volume(
            dataset_id=self.DATASET_ID, size=REALISTIC_BLOCKDEVICE_SIZE
        )
        volume = api.attach_volume(volume.blockdevice_id, self.NODE)

        deployer = BlockDeviceDeployer(
            hostname=self.NODE,
            block_device_api=api,
        )

        changes = deployer.calculate_changes(
            cluster_configuration, cluster_state,
        )

        self.assertEqual(
            in_parallel(changes=[
                DestroyBlockDeviceDataset(dataset_id=self.DATASET_ID)
            ]),
            changes
        )

    def test_deleted_dataset_belongs_to_other_node(self):
        """
        If a dataset with a primary manifestation on one node is marked as
        deleted in the configuration, the ``BlockDeviceDeployer`` for a
        different node does not return a ``DestroyBlockDeviceDataset`` from its
        ``calculate_necessary_state_changes`` for that dataset.
        """
        other_node = u"192.0.2.2"
        local_state = self.ONE_DATASET_STATE
        cluster_state = Deployment(
            nodes={to_node(local_state)}
        )

        local_config = to_node(local_state).transform(
            ["manifestations", unicode(self.DATASET_ID), "dataset", "deleted"],
            True
        )
        cluster_configuration = Deployment(
            nodes={local_config}
        )

        api = loopbackblockdeviceapi_for_test(self)
        volume = api.create_volume(
            dataset_id=self.DATASET_ID, size=REALISTIC_BLOCKDEVICE_SIZE
        )
        api.attach_volume(volume.blockdevice_id, self.NODE)

        deployer = BlockDeviceDeployer(
            # This deployer is responsible for *other_node*, not node.
            hostname=other_node,
            block_device_api=api,
        )

        changes = deployer.calculate_changes(
            cluster_configuration, cluster_state,
        )

        self.assertEqual(
            in_parallel(changes=[]),
            changes
        )


class BlockDeviceDeployerCreationCalculateChangesTests(
        SynchronousTestCase
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
        other_node = u"192.0.2.2"
        configuration = Deployment(
            nodes={
                Node(
                    hostname=other_node,
                    manifestations={dataset_id: manifestation},
                )
            }
        )
        state = DeploymentState(nodes=[])
        api = LoopbackBlockDeviceAPI.from_path(self.mktemp())
        deployer = BlockDeviceDeployer(
            hostname=node,
            block_device_api=api,
        )
        changes = deployer.calculate_changes(configuration, state)
        self.assertEqual(in_parallel(changes=[]), changes)

    def test_no_devices_one_dataset(self):
        """
        If no devices exist but a dataset is part of the configuration for the
        deployer's node, a ``CreateBlockDeviceDataset`` change is calculated.
        """
        dataset_id = unicode(uuid4())
        dataset = Dataset(dataset_id=dataset_id)
        manifestation = Manifestation(
            dataset=dataset, primary=True
        )
        node = u"192.0.2.1"
        configuration = Deployment(
            nodes={
                Node(
                    hostname=node,
                    manifestations={dataset_id: manifestation},
                )
            }
        )
        state = DeploymentState(nodes=[])
        api = LoopbackBlockDeviceAPI.from_path(self.mktemp())
        deployer = BlockDeviceDeployer(
            hostname=node,
            block_device_api=api,
        )
        changes = deployer.calculate_changes(configuration, state)
        mountpoint = deployer.mountroot.child(dataset_id.encode("ascii"))
        self.assertEqual(
            in_parallel(
                changes=[
                    CreateBlockDeviceDataset(
                        dataset=dataset, mountpoint=mountpoint
                    )
                ]),
            changes
        )

    def _calculate_changes(self, local_hostname, local_state,
                           desired_configuration):
        """
        Create a ``BlockDeviceDeployer`` and call its
        ``calculate_necessary_state_changes`` method with the given arguments
        and an empty cluster state.

        :param unicode local_hostname: The node identifier to give to the
            ``BlockDeviceDeployer``.
        :param desired_configuration: As accepted by
            ``IDeployer.calculate_changes``.

        :return: The return value of ``BlockDeviceDeployer.calculate_changes``.
        """
        # It is expected that someone will have merged local state into cluster
        # state.
        current_cluster_state = DeploymentState(nodes={local_state})

        api = LoopbackBlockDeviceAPI.from_path(self.mktemp())
        deployer = BlockDeviceDeployer(
            hostname=local_hostname,
            block_device_api=api,
        )

        return deployer.calculate_changes(
            desired_configuration, current_cluster_state
        )

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
            paths={
                expected_dataset_id: FilePath(b"/flocker").child(
                    expected_dataset_id.encode("ascii")),
            },
            manifestations={
                expected_dataset_id:
                Manifestation(
                    primary=True,
                    dataset=Dataset(
                        dataset_id=expected_dataset_id,
                        maximum_size=REALISTIC_BLOCKDEVICE_SIZE,
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
            manifestations=local_state.manifestations.transform(
                (expected_dataset_id, "dataset", "metadata"),
                {u"name": u"my_volume"}
            ))])
        actual_changes = self._calculate_changes(
            expected_hostname,
            local_state,
            desired_configuration
        )

        expected_changes = in_parallel(changes=[])

        self.assertEqual(expected_changes, actual_changes)


class IBlockDeviceAPITestsMixin(object):
    """
    Tests to perform on ``IBlockDeviceAPI`` providers.
    """
    def test_interface(self):
        """
        ``api`` instances provide ``IBlockDeviceAPI``.
        """
        self.assertTrue(
            verifyObject(IBlockDeviceAPI, self.api)
        )

    def test_list_volume_empty(self):
        """
        ``list_volumes`` returns an empty ``list`` if no block devices have
        been created.
        """
        self.assertEqual([], self.api.list_volumes())

    def test_created_is_listed(self):
        """
        ``create_volume`` returns a ``BlockVolume`` that is returned by
        ``list_volumes``.
        """
        dataset_id = uuid4()
        new_volume = self.api.create_volume(
            dataset_id=dataset_id,
            size=REALISTIC_BLOCKDEVICE_SIZE)
        self.assertIn(new_volume, self.api.list_volumes())

    def test_listed_volume_attributes(self):
        """
        ``list_volumes`` returns ``BlockVolume`` s that have a dataset_id.
        """
        expected_dataset_id = uuid4()
        self.api.create_volume(
            dataset_id=expected_dataset_id,
            size=REALISTIC_BLOCKDEVICE_SIZE
        )
        [listed_volume] = self.api.list_volumes()
        self.assertEqual(expected_dataset_id, listed_volume.dataset_id)

    def test_created_volume_attributes(self):
        """
        ``create_volume`` returns a ``BlockVolume`` that has a dataset_id
        """
        expected_dataset_id = uuid4()
        new_volume = self.api.create_volume(
            dataset_id=expected_dataset_id,
            size=REALISTIC_BLOCKDEVICE_SIZE
        )
        self.assertEqual(expected_dataset_id, new_volume.dataset_id)

    def test_attach_unknown_volume(self):
        """
        An attempt to attach an unknown ``BlockDeviceVolume`` raises
        ``UnknownVolume``.
        """
        self.assertRaises(
            UnknownVolume,
            self.api.attach_volume,
            blockdevice_id=unicode(uuid4()),
            # XXX This IP address and others in following tests need to be
            # parameterized so that these tests can be run against real cloud
            # nodes.
            host=u'192.0.2.123'
        )

    def test_attach_attached_volume(self):
        """
        An attempt to attach an already attached ``BlockDeviceVolume`` raises
        ``AlreadyAttachedVolume``.
        """
        host = u'192.0.2.123'
        dataset_id = uuid4()

        new_volume = self.api.create_volume(
            dataset_id=dataset_id,
            size=REALISTIC_BLOCKDEVICE_SIZE
        )
        attached_volume = self.api.attach_volume(
            new_volume.blockdevice_id, host=host
        )

        self.assertRaises(
            AlreadyAttachedVolume,
            self.api.attach_volume,
            blockdevice_id=attached_volume.blockdevice_id,
            host=host
        )

    def test_attach_elsewhere_attached_volume(self):
        """
        An attempt to attach a ``BlockDeviceVolume`` already attached to
        another host raises ``AlreadyAttachedVolume``.
        """
        new_volume = self.api.create_volume(
            dataset_id=uuid4(),
            size=REALISTIC_BLOCKDEVICE_SIZE
        )
        attached_volume = self.api.attach_volume(
            new_volume.blockdevice_id, host=u'192.0.2.123'
        )

        self.assertRaises(
            AlreadyAttachedVolume,
            self.api.attach_volume,
            blockdevice_id=attached_volume.blockdevice_id,
            host=u'192.0.2.124'
        )

    def test_attach_unattached_volume(self):
        """
        An unattached ``BlockDeviceVolume`` can be attached.
        """
        expected_host = u'192.0.2.123'
        dataset_id = uuid4()
        new_volume = self.api.create_volume(
            dataset_id=dataset_id,
            size=REALISTIC_BLOCKDEVICE_SIZE)
        expected_volume = BlockDeviceVolume(
            blockdevice_id=new_volume.blockdevice_id,
            size=new_volume.size,
            host=expected_host,
            dataset_id=dataset_id
        )
        attached_volume = self.api.attach_volume(
            blockdevice_id=new_volume.blockdevice_id,
            host=expected_host
        )
        self.assertEqual(expected_volume, attached_volume)

    def test_attached_volume_listed(self):
        """
        An attached ``BlockDeviceVolume`` is listed.
        """
        dataset_id = uuid4()
        expected_host = u'192.0.2.123'
        new_volume = self.api.create_volume(
            dataset_id=dataset_id,
            size=REALISTIC_BLOCKDEVICE_SIZE)
        expected_volume = BlockDeviceVolume(
            blockdevice_id=new_volume.blockdevice_id,
            size=new_volume.size,
            host=expected_host,
            dataset_id=dataset_id,
        )
        self.api.attach_volume(
            blockdevice_id=new_volume.blockdevice_id,
            host=expected_host
        )
        self.assertEqual([expected_volume], self.api.list_volumes())

    def test_list_attached_and_unattached(self):
        """
        ``list_volumes`` returns both attached and unattached
        ``BlockDeviceVolume``s.
        """
        expected_host = u'192.0.2.123'

        new_volume1 = self.api.create_volume(
            dataset_id=uuid4(),
            size=REALISTIC_BLOCKDEVICE_SIZE
        )
        new_volume2 = self.api.create_volume(
            dataset_id=uuid4(),
            size=REALISTIC_BLOCKDEVICE_SIZE
        )
        attached_volume = self.api.attach_volume(
            blockdevice_id=new_volume2.blockdevice_id,
            host=expected_host
        )
        self.assertItemsEqual(
            [new_volume1, attached_volume],
            self.api.list_volumes()
        )

    def test_multiple_volumes_attached_to_host(self):
        """
        ``attach_volume`` can attach multiple block devices to a single host.
        """
        expected_host = u'192.0.2.123'
        volume1 = self.api.create_volume(
            dataset_id=uuid4(),
            size=REALISTIC_BLOCKDEVICE_SIZE
        )
        volume2 = self.api.create_volume(
            dataset_id=uuid4(),
            size=REALISTIC_BLOCKDEVICE_SIZE
        )
        attached_volume1 = self.api.attach_volume(
            volume1.blockdevice_id, host=expected_host
        )
        attached_volume2 = self.api.attach_volume(
            volume2.blockdevice_id, host=expected_host
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
        unknown_blockdevice_id = unicode(uuid4())
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
            size=REALISTIC_BLOCKDEVICE_SIZE
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
            size=REALISTIC_BLOCKDEVICE_SIZE
        )
        attached_volume = self.api.attach_volume(
            new_volume.blockdevice_id,
            u'192.0.2.123'
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
            size=REALISTIC_BLOCKDEVICE_SIZE
        )
        attached_volume = self.api.attach_volume(
            new_volume.blockdevice_id,
            u'192.0.2.123'
        )

        device_path1 = self.api.get_device_path(attached_volume.blockdevice_id)
        device_path2 = self.api.get_device_path(attached_volume.blockdevice_id)

        self.assertEqual(device_path1, device_path2)

    def test_destroy_unknown_volume(self):
        """
        ``destroy_volume`` raises ``UnknownVolume`` if the supplied
        ``blockdevice_id`` does not exist.
        """
        blockdevice_id = unicode(uuid4)
        exception = self.assertRaises(
            UnknownVolume,
            self.api.destroy_volume, blockdevice_id=blockdevice_id
        )
        self.assertEqual(exception.args, (blockdevice_id,))

    def test_destroy_volume(self):
        """
        An unattached volume can be destroyed using ``destroy_volume``.
        """
        unrelated = self.api.create_volume(
            dataset_id=uuid4(),
            size=REALISTIC_BLOCKDEVICE_SIZE,
        )
        volume = self.api.create_volume(
            dataset_id=uuid4(),
            size=REALISTIC_BLOCKDEVICE_SIZE,
        )
        self.api.destroy_volume(volume.blockdevice_id)
        self.assertEqual([unrelated], self.api.list_volumes())

    def _destroyed_volume(self):
        """
        :return: A ``BlockDeviceVolume`` representing a volume which has been
            destroyed.
        """
        volume = self.api.create_volume(
            dataset_id=uuid4(), size=REALISTIC_BLOCKDEVICE_SIZE
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
        blockdevice_id = unicode(uuid4)
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
            dataset_id=uuid4(), size=REALISTIC_BLOCKDEVICE_SIZE
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

        node = u"192.0.2.1"

        # Create an unrelated, attached volume that should be undisturbed.
        unrelated = self.api.create_volume(
            dataset_id=uuid4(), size=REALISTIC_BLOCKDEVICE_SIZE
        )
        unrelated = self.api.attach_volume(unrelated.blockdevice_id, node)

        # Create the volume we'll detach.
        volume = self.api.create_volume(
            dataset_id=uuid4(), size=REALISTIC_BLOCKDEVICE_SIZE
        )
        volume = self.api.attach_volume(
            volume.blockdevice_id, node
        )

        device_path = self.api.get_device_path(volume.blockdevice_id)

        attached_error = fail_mount(device_path)

        self.api.detach_volume(volume.blockdevice_id)

        self.assertEqual(
            {unrelated, volume.set(host=None)},
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
        node = u"192.0.2.4"
        # Create the volume we'll detach.
        volume = self.api.create_volume(
            dataset_id=uuid4(), size=REALISTIC_BLOCKDEVICE_SIZE
        )
        attached_volume = self.api.attach_volume(
            volume.blockdevice_id, node
        )
        self.api.detach_volume(volume.blockdevice_id)
        reattached_volume = self.api.attach_volume(
            volume.blockdevice_id, node
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
        node = u"192.0.2.5"
        volume = self._destroyed_volume()
        exception = self.assertRaises(
            UnknownVolume,
            self.api.attach_volume, volume.blockdevice_id, node
        )
        self.assertEqual(exception.args, (volume.blockdevice_id,))


def make_iblockdeviceapi_tests(blockdevice_api_factory):
    """
    :returns: A ``TestCase`` with tests that will be performed on the
       supplied ``IBlockDeviceAPI`` provider.
    """
    class Tests(IBlockDeviceAPITestsMixin, SynchronousTestCase):
        def setUp(self):
            self.api = blockdevice_api_factory(test_case=self)

    return Tests


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


def loopbackblockdeviceapi_for_test(test_case):
    """
    :returns: A ``LoopbackBlockDeviceAPI`` with a temporary root directory
        created for the supplied ``test_case``.
    """
    user_id = os.getuid()
    if user_id != 0:
        raise SkipTest(
            "``LoopbackBlockDeviceAPI`` uses ``losetup``, "
            "which requires root privileges. "
            "Required UID: 0, Found UID: {!r}".format(user_id)
        )

    root_path = test_case.mktemp()
    test_case.addCleanup(losetup_detach_all, FilePath(root_path))
    return LoopbackBlockDeviceAPI.from_path(root_path=root_path)


class LoopbackBlockDeviceAPITests(
        make_iblockdeviceapi_tests(
            blockdevice_api_factory=loopbackblockdeviceapi_for_test
        )
):
    """
    Interface adherence Tests for ``LoopbackBlockDeviceAPI``.
    """


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

        LoopbackBlockDeviceAPI.from_path(directory.path)

        self.assertTrue(
            (True, True),
            (attached_directory.exists(), unattached_directory.exists())
        )

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
        api = loopbackblockdeviceapi_for_test(test_case=self)
        # 1GB
        apparent_size = REALISTIC_BLOCKDEVICE_SIZE
        volume = api.create_volume(
            dataset_id=uuid4(),
            size=apparent_size
        )
        backing_file = api._root_path.descendant(
            ['unattached', volume.blockdevice_id]
        )
        # Get actual number of 512 byte blocks used by the file.
        # See http://stackoverflow.com/a/3212102
        actual_size = os.stat(backing_file.path).st_blocks * 512
        reported_size = backing_file.getsize()

        self.assertEqual(
            (0, apparent_size),
            (actual_size, reported_size)
        )

    def test_list_unattached_volumes(self):
        """
        ``list_volumes`` returns a ``BlockVolume`` for each unattached volume
        file.
        """
        expected_size = REALISTIC_BLOCKDEVICE_SIZE
        api = loopbackblockdeviceapi_for_test(test_case=self)
        expected_dataset_id = uuid4()
        blockdevice_volume = _blockdevicevolume_from_dataset_id(
            size=expected_size,
            dataset_id=expected_dataset_id,
        )
        with (api._root_path
              .child('unattached')
              .child(blockdevice_volume.blockdevice_id.encode('ascii'))
              .open('wb')) as f:
            f.truncate(expected_size)
        self.assertEqual([blockdevice_volume], api.list_volumes())

    def test_list_attached_volumes(self):
        """
        ``list_volumes`` returns a ``BlockVolume`` for each attached volume
        file.
        """
        expected_size = REALISTIC_BLOCKDEVICE_SIZE
        expected_host = u'192.0.2.123'
        expected_dataset_id = uuid4()
        api = loopbackblockdeviceapi_for_test(test_case=self)

        blockdevice_volume = _blockdevicevolume_from_dataset_id(
            size=expected_size,
            host=expected_host,
            dataset_id=expected_dataset_id,
        )

        host_dir = api._root_path.descendant([
            b'attached', expected_host.encode("utf-8")
        ])
        host_dir.makedirs()
        with host_dir.child(blockdevice_volume.blockdevice_id).open('wb') as f:
            f.truncate(expected_size)

        self.assertEqual([blockdevice_volume], api.list_volumes())


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


class _StateChangeTestsMixin(object):
    """
    Implementation of the general tests generated by
    ``make_state_change_tests``.
    """
    state_change = None

    def test_interface(self):
        """
        Instances of the type provide ``IStateChange``.
        """
        self.assertTrue(verifyObject(IStateChange, self.state_change()))


def make_state_change_tests(state_change):
    """
    Make some general tests that apply to any ``IStateChange`` implementation.

    :param state_change: A no-argument callable that returns the
        ``IStateChange`` provider to be tested.
    """
    class Tests(SynchronousTestCase, _StateChangeTestsMixin):
        def setUp(self):
            self.state_change = state_change
    return Tests


_ARBITRARY_VOLUME = BlockDeviceVolume(
    blockdevice_id=u"abcd",
    size=REALISTIC_BLOCKDEVICE_SIZE,
    dataset_id=uuid4(),
)


def _make_destroy_dataset():
    """
    Make a ``DestroyBlockDeviceDataset`` instance for
    ``make_state_change_tests``.
    """
    return DestroyBlockDeviceDataset(
        dataset_id=_ARBITRARY_VOLUME.dataset_id,
    )


class DestroyBlockDeviceDatasetTests(
        make_state_change_tests(_make_destroy_dataset)
):
    """
    Tests for ``DestroyBlockDeviceDataset``.
    """
    def test_dataset_id_required(self):
        """
        If ``dataset_id`` is not supplied when initializing
        ``DestroyBlockDeviceDataset``, ``InvariantException`` is raised.
        """
        self.assertRaises(InvariantException, DestroyBlockDeviceDataset)

    def test_dataset_id_must_be_uuid(self):
        """
        If the value given for ``dataset_id`` is not an instance of ``UUID``
        when initializing ``DestroyBlockDeviceDataset``, ``TypeError`` is
        raised.
        """
        self.assertRaises(
            TypeError, DestroyBlockDeviceDataset, dataset_id=object()
        )

    def test_equal(self):
        """
        Two ``DestroyBlockDeviceDataset`` instances compare as equal if they
        are initialized with the same dataset identifier.
        """
        dataset_id = unicode(uuid4())
        # Avoid using the same instance, just provide the same value.
        a = DestroyBlockDeviceDataset(dataset_id=UUID(dataset_id))
        b = DestroyBlockDeviceDataset(dataset_id=UUID(dataset_id))
        self.assertTrue(a == b)

    def test_not_equal(self):
        """
        Two ``DestroyBlockDeviceDataset`` instances compare as not equal if
        they are initialized with different dataset identifiers.
        """
        a = DestroyBlockDeviceDataset(dataset_id=uuid4())
        b = DestroyBlockDeviceDataset(dataset_id=uuid4())
        self.assertTrue(a != b)

    def verify_run_log(self, logger):
        # One action is logged
        [action] = LoggedAction.of_type(
            logger.messages, DESTROY_BLOCK_DEVICE_DATASET
        )
        # Child actions are logged
        [unmount] = LoggedAction.of_type(logger.messages, UNMOUNT_BLOCK_DEVICE)
        [detach] = LoggedAction.of_type(logger.messages, DETACH_VOLUME)
        [destroy] = LoggedAction.of_type(logger.messages, DESTROY_VOLUME)
        self.assertEqual([unmount, detach, destroy], action.children)

    @validate_logging(verify_run_log)
    def test_run(self, logger):
        """
        After running ``DestroyBlockDeviceDataset``, its volume has been
        unmounted, detached, and destroyed.
        """
        self.patch(blockdevice, "_logger", logger)

        node = u"192.0.2.3"
        dataset_id = uuid4()
        api = loopbackblockdeviceapi_for_test(self)
        volume = api.create_volume(
            dataset_id=dataset_id, size=REALISTIC_BLOCKDEVICE_SIZE
        )
        volume = api.attach_volume(volume.blockdevice_id, node)
        device = api.get_device_path(volume.blockdevice_id)
        mountroot = mountroot_for_test(self)
        mountpoint = mountroot.child(unicode(dataset_id).encode("ascii"))
        mountpoint.makedirs()
        make_filesystem(device, block_device=True)
        mount(device, mountpoint)

        deployer = BlockDeviceDeployer(
            hostname=node,
            block_device_api=api,
            mountroot=mountroot,
        )
        change = DestroyBlockDeviceDataset(dataset_id=dataset_id)
        self.successResultOf(change.run(deployer))

        # It's only possible to destroy a volume that's been detached.  It's
        # only possible to detach a volume that's been unmounted.  If the
        # volume doesn't exist, all three things we wanted to happen have
        # happened.
        self.assertEqual([], api.list_volumes())


def _make_unmount():
    """
    Make an ``UnmountBlockDevice`` instance for ``make_state_change_tests``.
    """
    return UnmountBlockDevice(
        volume=_ARBITRARY_VOLUME,
    )


class UnmountBlockDeviceTests(make_state_change_tests(_make_unmount)):
    """
    Tests for ``UnmountBlockDevice``.
    """
    def test_run(self):
        """
        ``UnmountBlockDevice.run`` unmounts the filesystem / block device
        associated with the volume passed to it (association as determined by
        the deployer's ``IBlockDeviceAPI`` provider).
        """
        node = u"192.0.2.1"
        dataset_id = uuid4()
        api = loopbackblockdeviceapi_for_test(self)
        volume = api.create_volume(
            dataset_id=dataset_id, size=REALISTIC_BLOCKDEVICE_SIZE
        )
        volume = api.attach_volume(volume.blockdevice_id, node)
        device = api.get_device_path(volume.blockdevice_id)
        mountroot = mountroot_for_test(self)
        mountpoint = mountroot.child(unicode(dataset_id).encode("ascii"))
        mountpoint.makedirs()
        make_filesystem(device, block_device=True)
        check_output([b"mount", device.path, mountpoint.path])

        deployer = BlockDeviceDeployer(
            hostname=node,
            block_device_api=api,
            mountroot=mountroot,
        )

        change = UnmountBlockDevice(volume=volume)
        self.successResultOf(change.run(deployer))
        self.assertNotIn(
            device,
            list(
                FilePath(partition.device)
                for partition
                in psutil.disk_partitions()
            )
        )


def _make_detach():
    """
    Make a ``DetachVolume`` for ``make_state_change_tests``.
    """
    return DetachVolume(
        volume=_ARBITRARY_VOLUME,
    )


class DetachVolumeTests(make_state_change_tests(_make_detach)):
    """
    Tests for ``DetachVolume``.
    """
    def test_run(self):
        """
        ``DetachVolume.run`` uses the deployer's ``IBlockDeviceAPI`` to detach
        its volume from the deployer's node.
        """
        node = u"192.0.2.1"
        dataset_id = uuid4()
        api = loopbackblockdeviceapi_for_test(self)
        volume = api.create_volume(
            dataset_id=dataset_id, size=REALISTIC_BLOCKDEVICE_SIZE
        )
        volume = api.attach_volume(volume.blockdevice_id, node)

        deployer = BlockDeviceDeployer(
            hostname=node,
            block_device_api=api,
        )

        change = DetachVolume(volume=volume)
        self.successResultOf(change.run(deployer))

        [volume] = api.list_volumes()
        self.assertIs(None, volume.host)


def _make_destroy_volume():
    """
    Make a ``DestroyVolume`` for ``make_state_change_tests``.
    """
    return DestroyVolume(
        volume=_ARBITRARY_VOLUME,
    )


class DestroyVolumeTests(make_state_change_tests(_make_destroy_volume)):
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
        api = loopbackblockdeviceapi_for_test(self)
        volume = api.create_volume(
            dataset_id=dataset_id, size=REALISTIC_BLOCKDEVICE_SIZE
        )

        deployer = BlockDeviceDeployer(
            hostname=node,
            block_device_api=api,
        )

        change = DestroyVolume(volume=volume)
        self.successResultOf(change.run(deployer))

        self.assertEqual([], api.list_volumes())


def _make_create():
    """
    Make a ``CreateBlockDeviceDataset`` for ``make_state_change_tests``.
    """
    return CreateBlockDeviceDataset(
        dataset=Dataset(dataset_id=unicode(uuid4())),
        mountpoint=FilePath('.')
    )


class CreateBlockDeviceDatasetTests(make_state_change_tests(_make_create)):
    """
    Tests for ``CreateBlockDeviceDataset``.
    """
    def _create_blockdevice_dataset(self, host, dataset_id, maximum_size):
        """
        Call ``CreateBlockDeviceDataset.run`` with a ``BlockDeviceDeployer``.

        :param unicode host: The IP address of the host for the deployer.
        :param UUID dataset_id: The uuid4 identifier for the dataset which will
            be created.
        :param int maximum_size: The size, in bytes, of the dataset which will
            be created.
        :returns: A 3-tuple of:
            * ``BlockDeviceVolume`` created by the run operation
            * The ``FilePath`` of the device where the volume is attached.
            * The ``FilePath`` where the volume is expected to be mounted.
        """
        api = loopbackblockdeviceapi_for_test(self)
        mountroot = mountroot_for_test(self)
        expected_mountpoint = mountroot.child(
            unicode(dataset_id).encode("ascii")
        )

        deployer = BlockDeviceDeployer(
            hostname=host,
            block_device_api=api,
            mountroot=mountroot
        )

        dataset = Dataset(
            dataset_id=unicode(dataset_id),
            maximum_size=maximum_size,
        )

        change = CreateBlockDeviceDataset(
            dataset=dataset, mountpoint=expected_mountpoint
        )

        change.run(deployer)

        [volume] = api.list_volumes()
        device_path = api.get_device_path(volume.blockdevice_id)

        return volume, device_path, expected_mountpoint

    def test_run_create(self):
        """
        ``CreateBlockDeviceDataset.run`` uses the ``IDeployer``\ 's API object
        to create a new volume.
        """
        host = u"192.0.2.1"
        dataset_id = uuid4()
        maximum_size = REALISTIC_BLOCKDEVICE_SIZE

        (volume,
         device_path,
         expected_mountpoint) = self._create_blockdevice_dataset(
            host=host,
            dataset_id=dataset_id,
            maximum_size=maximum_size
        )

        expected_volume = _blockdevicevolume_from_dataset_id(
            dataset_id=dataset_id, host=host, size=maximum_size,
        )

        self.assertEqual(expected_volume, volume)

    def test_run_mkfs_and_mount(self):
        """
        ``CreateBlockDeviceDataset.run`` initializes the attached block device
        with an ext4 filesystem and mounts it.
        """
        host = u"192.0.2.1"
        dataset_id = uuid4()
        maximum_size = REALISTIC_BLOCKDEVICE_SIZE

        (volume,
         device_path,
         expected_mountpoint) = self._create_blockdevice_dataset(
            host=host,
            dataset_id=dataset_id,
            maximum_size=maximum_size
        )

        self.assertIn(
            (device_path.path, expected_mountpoint.path, b"ext4"),
            list(
                (partition.device, partition.mountpoint, partition.fstype)
                for partition
                in psutil.disk_partitions()
            )
        )
