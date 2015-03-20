# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for ``flocker.node.agents.blockdevice``.
"""

import os
from uuid import uuid4
from subprocess import check_output

from zope.interface.verify import verifyObject

from twisted.python.filepath import FilePath
from twisted.trial.unittest import SynchronousTestCase, SkipTest

from ..blockdevice import (
    BlockDeviceDeployer, LoopbackBlockDeviceAPI, IBlockDeviceAPI,
    BlockDeviceVolume, UnknownVolume, AlreadyAttachedVolume,
    CreateBlockDeviceDataset, UnattachedVolume,
    _losetup_list_parse, _losetup_list,
)

from ... import InParallel, IDeployer, IStateChange
from ....control import Dataset, Manifestation, Node, NodeState, Deployment

GIBIBYTE = 2 ** 30
REALISTIC_BLOCKDEVICE_SIZE = 4 * GIBIBYTE


class BlockDeviceDeployerTests(SynchronousTestCase):
    """
    Tests for ``BlockDeviceDeployer``.
    """
    def test_interface(self):
        """
        ``BlockDeviceDeployer`` instances provide ``IDeployer``.
        """
        api = LoopbackBlockDeviceAPI.from_path(self.mktemp())
        self.assertTrue(
            verifyObject(
                IDeployer,
                BlockDeviceDeployer(
                    hostname=u'192.0.2.123',
                    block_device_api=api
                )
            )
        )


class BlockDeviceDeployerDiscoverLocalStateTests(SynchronousTestCase):
    """
    Tests for ``BlockDeviceDeployer.discover_local_state``.
    """
    def setUp(self):
        self.expected_hostname = u'192.0.2.123'
        self.api = loopbackblockdeviceapi_for_test(self)
        self.deployer = BlockDeviceDeployer(
            hostname=self.expected_hostname,
            block_device_api=self.api
        )

    def assertDiscoveredState(self, deployer, expected_manifestations):
        """
        Assert that the manifestations on the state object returned by
        ``deployer.discover_local_state`` equals the given list of
        manifestations.

        :param IDeployer deployer: The object to use to discover the state.
        :param list expected_manifestations: The ``Manifestation``\ s expected
            to be discovered.

        :raise: A test failure exception if the manifestations are not what is
            expected.
        """
        discovering = deployer.discover_local_state()
        state = self.successResultOf(discovering)
        expected_paths = {}
        for manifestation in expected_manifestations:
            dataset_id = manifestation.dataset.dataset_id
            mountpath = deployer._mountpath_for_manifestation(manifestation)
            expected_paths[dataset_id] = mountpath
        self.assertEqual(
            NodeState(
                hostname=deployer.hostname,
                running=(),
                not_running=(),
                manifestations=expected_manifestations,
                paths=expected_paths,
            ),
            state
        )

    def test_no_devices(self):
        """
        ``BlockDeviceDeployer.discover_local_state`` returns a ``NodeState``
        with empty ``manifestations`` if the ``api`` reports no locally
        attached volumes.
        """
        self.assertDiscoveredState(self.deployer, [])

    def test_one_device(self):
        """
        ``BlockDeviceDeployer.discover_local_state`` returns a ``NodeState``
        with one ``manifestations`` if the ``api`` reports one locally
        attached volumes.
        """
        dataset_id = uuid4()
        new_volume = self.api.create_volume(
            dataset_id=dataset_id,
            size=REALISTIC_BLOCKDEVICE_SIZE
        )
        self.api.attach_volume(
            new_volume.blockdevice_id, self.expected_hostname
        )
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
        ``BlockDeviceDeployer.discover_local_state`` does not consider remotely
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
        ``BlockDeviceDeployer.discover_local_state`` does not consider
        unattached volumes.
        """
        dataset_id = uuid4()
        self.api.create_volume(
            dataset_id=dataset_id,
            size=REALISTIC_BLOCKDEVICE_SIZE)
        self.assertDiscoveredState(self.deployer, [])


class BlockDeviceDeployerCalculateNecessaryStateChangesTests(
        SynchronousTestCase
):
    """
    Tests for ``BlockDeviceDeployer.calculate_necessary_state_changes``.
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
            nodes=frozenset({
                Node(
                    hostname=other_node,
                    manifestations={dataset_id: manifestation},
                )
            })
        )
        state = Deployment(nodes=frozenset())
        api = LoopbackBlockDeviceAPI.from_path(self.mktemp())
        deployer = BlockDeviceDeployer(
            hostname=node,
            block_device_api=api,
        )
        changes = deployer.calculate_necessary_state_changes(
            local_state=NodeState(hostname=node),
            desired_configuration=configuration,
            current_cluster_state=state,
        )
        self.assertEqual(InParallel(changes=[]), changes)

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
            nodes=frozenset({
                Node(
                    hostname=node,
                    manifestations={dataset_id: manifestation},
                )
            })
        )
        state = Deployment(nodes=frozenset())
        api = LoopbackBlockDeviceAPI.from_path(self.mktemp())
        deployer = BlockDeviceDeployer(
            hostname=node,
            block_device_api=api,
        )
        changes = deployer.calculate_necessary_state_changes(
            local_state=NodeState(hostname=node),
            desired_configuration=configuration,
            current_cluster_state=state,
        )
        mountpoint = deployer.mountroot.child(dataset_id.encode("ascii"))
        self.assertEqual(
            InParallel(
                changes=[
                    CreateBlockDeviceDataset(
                        dataset=dataset, mountpoint=mountpoint
                    )
                ]),
            changes
        )

    def _calculate_changes(self, local_hostname, local_state, desired_configuration):
        # Control service still reports that this node has no manifestations.
        current_cluster_state = Deployment(
            nodes=frozenset([Node(hostname=local_hostname)])
        )

        # API shouldn't be called upon
        api = object()
        deployer = BlockDeviceDeployer(
            hostname=local_hostname,
            block_device_api=api,
        )

        return deployer.calculate_necessary_state_changes(
            local_state, desired_configuration, current_cluster_state
        )


    def test_local_state_overrides_cluster_state(self):
        """
        ``BlockDeviceDeployer.calculate_necessary_state_changes`` uses the
        given local state to override cluster state, since the latter may be
        stale.

        XXX: This may not be necessary since we don't currently use
        cluster_state in our state change calculation.
        """
        local_hostname = u"192.0.2.1"
        dataset_id = unicode(uuid4())
        dataset = Dataset(dataset_id=dataset_id)
        manifestation = Manifestation(
            dataset=dataset, primary=True
        )

        # Discovered local state reveals the configured manifestation is
        # already on this node.
        local_state = NodeState(
            hostname=local_hostname,
            manifestations=[manifestation],
            paths={dataset_id: FilePath('/foo/bar')}
        )

        # Configuration requires a manifestation on this node.
        desired_configuration = Deployment(
            nodes=frozenset({
                Node(
                    hostname=local_hostname,
                    manifestations={dataset_id: manifestation},
                )
            })
        )

        actual_changes = self._calculate_changes(local_hostname, local_state, desired_configuration)

        # If Deployer is buggy and not overriding cluster state
        # with local state this would result in a dataset creation action:
        expected_changes = InParallel(changes=[])

        self.assertEqual(expected_changes, actual_changes)

    def test_match_configuration_to_state_of_datasets(self):
        """
        Dataset creation state changes are calculated by dataset_id only.
        Discovered datasets with different attributes to those in the
        configuration do not result in ``CreateBlockDeviceDataset`` state
        changes.
        """
        expected_hostname = u'192.0.2.123'
        expected_dataset_id = unicode(uuid4())
        local_state = NodeState(
            hostname=expected_hostname,
            paths={
                expected_dataset_id: FilePath(
                    u'/flocker/{}'.format(expected_dataset_id)
                )
            },
            manifestations=[
                Manifestation(
                    primary=True,
                    dataset=Dataset(
                        dataset_id=expected_dataset_id,
                        maximum_size=REALISTIC_BLOCKDEVICE_SIZE,
                        # Dataset state will always have empty metadata and
                        # deleted will always be False.
                        metadata={},
                        deleted=False,
                    )
                ),
            ]
        )

        desired_configuration = Deployment(
            nodes=[
                Node(
                    hostname=expected_hostname,
                    manifestations={
                        expected_dataset_id: Manifestation(
                            primary=True,
                            dataset=Dataset(
                                dataset_id=expected_dataset_id,
                                maximum_size=REALISTIC_BLOCKDEVICE_SIZE,
                                # Configuration contains metadata and deleted
                                # attributes, but the state will always have
                                # empty metadata and deleted=False, never True.
                                metadata={"name": "my_volume"},
                                deleted=False,
                            )
                        )
                    }
                )
            ]
        )

        actual_changes = self._calculate_changes(
            expected_hostname,
            local_state,
            desired_configuration
        )

        expected_changes = InParallel(changes=[])

        self.assertEqual(expected_changes, actual_changes)

    def test_ignore_deleted_datasets(self):
        """
        Deleted datasets in the supplied configuration do not result in
        ``CreateBlockDeviceDataset`` changes.
        """
        expected_hostname = u'192.0.2.123'
        expected_dataset_id = unicode(uuid4())
        local_state = NodeState(
            hostname=expected_hostname,
            paths={},
            manifestations=[]
        )

        desired_configuration = Deployment(
            nodes=[
                Node(
                    hostname=expected_hostname,
                    manifestations={
                        expected_dataset_id: Manifestation(
                            primary=True,
                            dataset=Dataset(
                                dataset_id=expected_dataset_id,
                                maximum_size=REALISTIC_BLOCKDEVICE_SIZE,
                                # There's a dataset in the configuration but
                                # it's deleted and should not be recreated.
                                deleted=True,
                            )
                        )
                    }
                )
            ]
        )

        actual_changes = self._calculate_changes(
            expected_hostname,
            local_state,
            desired_configuration
        )
        expected_changes = InParallel(changes=[])

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
        blockdevice_volume = BlockDeviceVolume.from_dataset_id(
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

        blockdevice_volume = BlockDeviceVolume.from_dataset_id(
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
    for device_file, mountpoint_directory, filesystem_type in get_mounts():
        try:
            mountpoint_directory.segmentsFrom(root_path)
        except ValueError:
            pass
        else:
            umount(device_file)


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


class CreateBlockDeviceDatasetTests(SynchronousTestCase):
    """
    Tests for ``CreateBlockDeviceDataset``.
    """
    def test_interface(self):
        """
        ``CreateBlockDeviceDataset`` provides ``IStateChange``.
        """
        self.assertTrue(
            verifyObject(
                IStateChange,
                CreateBlockDeviceDataset(
                    dataset=Dataset(dataset_id=unicode(uuid4())),
                    mountpoint=FilePath('.')
                )
            )
        )

    def test_run(self):
        """
        ``CreateBlockDeviceDataset.run`` uses the ``IDeployer``\ 's API object
        to create a new volume, attach it to the deployer's node, initialize
        the resulting block device with a filesystem, and mount the filesystem.
        """
        host = u"192.0.2.1"
        mountroot = mountroot_for_test(self)
        api = loopbackblockdeviceapi_for_test(self)
        deployer = BlockDeviceDeployer(
            hostname=host, block_device_api=api, mountroot=mountroot
        )
        dataset_id = uuid4()
        mountpoint = mountroot.child(unicode(dataset_id).encode("ascii"))
        dataset = Dataset(
            dataset_id=unicode(dataset_id),
            maximum_size=REALISTIC_BLOCKDEVICE_SIZE
        )
        change = CreateBlockDeviceDataset(
            dataset=dataset, mountpoint=mountpoint
        )
        change.run(deployer)

        [volume] = api.list_volumes()

        expected_volume = BlockDeviceVolume.from_dataset_id(
            dataset_id=dataset_id, host=host, size=dataset.maximum_size,
        )

        self.assertEqual(expected_volume, volume)

        mounts = list(get_mounts())

        self.assertIn(
            (api.get_device_path(volume.blockdevice_id),
             mountpoint,
             b"ext4"),
            mounts
        )


def get_mounts():
    """
    :returns: A generator 3-tuple(device_path, mountpoint, filesystem_type) for
        each currently mounted filesystem reported in ``/proc/self/mounts``.
    """
    with open("/proc/self/mounts") as mounts:
        for mount in mounts:
            device_path, mountpoint, filesystem_type = mount.split()[:3]
            yield FilePath(device_path), FilePath(mountpoint), filesystem_type
