# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Test helpers for ``flocker.node.agents.blockdevice``.
"""
from os import environ
from unittest import SkipTest, skipUnless
from subprocess import check_output, Popen, PIPE, STDOUT
import time
from uuid import uuid4

import psutil

import yaml
from bitmath import GiB

from eliot import (
    Logger,
    Message,
    start_action,
    write_traceback,
)

from testtools.matchers import AllMatch, IsInstance

from twisted.internet import reactor
from twisted.python.components import proxyForInterface
from twisted.python.filepath import FilePath

from zope.interface import implementer
from zope.interface.verify import verifyObject

from ....testtools import TestCase, AsyncTestCase
from ....testtools.cluster_utils import make_cluster_id, TestTypes, Providers
from ....common import RACKSPACE_MINIMUM_VOLUME_SIZE

from ..blockdevice import (
    AlreadyAttachedVolume,
    BlockDeviceVolume,
    IBlockDeviceAPI,
    ICloudAPI,
    IProfiledBlockDeviceAPI,
    MandatoryProfiles,
    UnattachedVolume,
    UnknownVolume,
    _SyncToThreadedAsyncCloudAPIAdapter,
    allocated_size,
    get_blockdevice_volume,
)

from ..loopback import check_allocatable_size
from ..cinder import cinder_from_configuration
from ..ebs import EBSBlockDeviceAPI, ec2_client
from ..gce import gce_from_configuration


# Eliot is transitioning away from the "Logger instances all over the place"
# approach. So just use this global logger for now.
_logger = Logger()

CLEANUP_RETRY_LIMIT = 10


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


class IBlockDeviceAPITestsMixin(object):
    """
    Tests to perform on ``IBlockDeviceAPI`` providers.
    """
    this_node = None

    def repeat_retries(self):
        """
        @return: An iterable of delay intervals, measured in seconds, used
             to retry in ``repeat_until_consistent``. By default only one
             try is allowed; subclasses can override to change this
             policy.
        """
        return [0]

    def repeat_until_consistent(self, f, *args, **kwargs):
        """
        Repeatedly call a function with given arguments until AssertionErrors
        stop or configured number of repetitions are reached.

        Some backends are eventually consistent, which means results of
        listing volumes may not reflect actions immediately. So for
        read-only operations that rely on listing we want to be able to
        retry.

        Retry policy can be changed by overriding the ``repeat_retries``
        method.

        @param f: Function to call.
        @param args: Arguments for ``f``.
        @param kwargs: Keyword arguments for ``f``.
        """
        for step in self.repeat_retries():
            try:
                return f(*args, **kwargs)
            except AssertionError as e:
                time.sleep(step)
        raise e

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
        if self.device_allocation_unit is None:
            expected_device_size = expected_volume_size
        else:
            expected_device_size = allocated_size(
                self.device_allocation_unit, expected_volume_size
            )

        # Attach it, so that we can measure its size, as reported by
        # the kernel of the machine to which it's attached.
        self.api.attach_volume(
            volume.blockdevice_id, attach_to=self.this_node,
        )

        def validate(volume):
            # Reload the volume using ``IBlockDeviceAPI.list_volumes`` in
            # case the implementation hasn't verified that the requested
            # size has actually been stored.
            volume = get_blockdevice_volume(self.api, volume.blockdevice_id)

            device_path = self.api.get_device_path(volume.blockdevice_id).path

            command = [b"/bin/lsblk", b"--noheadings", b"--bytes",
                       b"--output", b"SIZE", device_path.encode("ascii")]
            command_output = check_output(command).split(b'\n')[0]
            device_size = int(command_output.strip().decode("ascii"))
            self.assertEqual(
                (expected_volume_size, expected_device_size),
                (volume.size, device_size)
            )
        self.repeat_until_consistent(validate, volume)

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
        self.repeat_until_consistent(
            lambda: self.assertIn(new_volume, self.api.list_volumes()))

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

        def validate():
            listed_volumes = self.api.list_volumes()
            # Ideally we wouldn't two two assertions, but it's the easiest
            # thing to do that works with the retry logic.
            self.assertEqual(len(listed_volumes), 1)
            listed_volume = listed_volumes[0]

            self.assertEqual(
                (expected_dataset_id, self.minimum_allocatable_size),
                (listed_volume.dataset_id, listed_volume.size)
            )
        self.repeat_until_consistent(validate)

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
        self.repeat_until_consistent(
            lambda: self.assertEqual([expected_volume],
                                     self.api.list_volumes()))

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
        self.repeat_until_consistent(
            lambda: self.assertItemsEqual(
                [new_volume1, attached_volume],
                self.api.list_volumes()
            ))

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

        self.repeat_until_consistent(
            lambda: self.assertItemsEqual(
                [attached_volume1, attached_volume2],
                self.api.list_volumes()
            ))

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
        self.repeat_until_consistent(
            lambda: self.assertEqual([unrelated],
                                     self.api.list_volumes()))

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

        self.repeat_until_consistent(
            lambda: self.assertEqual(
                {unrelated, volume.set(attached_to=None)},
                set(self.api.list_volumes())
            ))

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
        self.repeat_until_consistent(
            lambda: self.assertEqual(
                (attached_volume, [attached_volume]),
                (reattached_volume, self.api.list_volumes())
            ))

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
    class Tests(IBlockDeviceAPITestsMixin, TestCase):
        def setUp(self):
            super(Tests, self).setUp()
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

    partitions_under_root = list(p for p in psutil.disk_partitions()
                                 if is_under_root(p.mountpoint))
    for partition in partitions_under_root:
        umount(FilePath(partition.mountpoint))


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
    class Tests(AsyncTestCase):
        def setUp(self):
            super(Tests, self).setUp()
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

        def test_list_live_nodes(self):
            """
            ``list_live_nodes`` returns an iterable of unicode values.
            """
            live_nodes = self.api.list_live_nodes()
            self.assertThat(live_nodes, AllMatch(IsInstance(unicode)))

    return Tests


@implementer(ICloudAPI)
class FakeCloudAPI(proxyForInterface(IBlockDeviceAPI)):
    """
    Wrap a ``IBlockDeviceAPI`` and also provide ``ICloudAPI``.
    """
    def __init__(self, block_api, live_nodes=()):
        """
        @param block_api: ``IBlockDeviceAPI`` to wrap.
        @param live_nodes: Live nodes beyond the current one.
        """
        self.original = block_api
        self.live_nodes = live_nodes

    def list_live_nodes(self):
        return [self.compute_instance_id()] + list(self.live_nodes)

    def start_node(self, node_id):
        return


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
    class Tests(IProfiledBlockDeviceAPITestsMixin, TestCase):
        def setUp(self):
            super(Tests, self).setUp()
            self.api = profiled_blockdevice_api_factory(self)
            self.dataset_size = dataset_size

    return Tests


class InvalidConfig(Exception):
    """
    The cloud configuration could not be found or is not compatible with the
    running environment.
    """


# XXX Remember to comment on or close FLOC-2584.


def get_blockdeviceapi():
    """
    Validate and load cloud provider's yml config file.
    Default to ``~/acceptance.yml`` in the current user home directory, since
    that's where buildbot puts its acceptance test credentials file.
    """
    config = get_blockdevice_config()
    backend_name = config.pop('backend')
    provider = Providers.lookupByName(backend_name.upper())
    factory = _BLOCKDEVICE_TYPES[provider]
    return factory(make_cluster_id(TestTypes.FUNCTIONAL, provider), config)


def get_blockdevice_config():
    """
    Get configuration dictionary suitable for use in the instantiation
    of an ``IBlockDeviceAPI`` implementation.

    :raises: ``InvalidConfig`` if a
        ``FLOCKER_FUNCTIONAL_TEST_CLOUD_CONFIG_FILE`` was not set and the
        default config file could not be read.

    :return: XXX
    """
    flocker_functional_test = environ.get('FLOCKER_FUNCTIONAL_TEST')
    if flocker_functional_test is None:
        raise SkipTest(
            'Please set FLOCKER_FUNCTIONAL_TEST environment variable to '
            'run storage backend functional tests.'
        )

    config_file_path = environ.get('FLOCKER_FUNCTIONAL_TEST_CLOUD_CONFIG_FILE')
    if config_file_path is None:
        raise SkipTest(
            'Supply the path to a backend configuration file '
            'using the FLOCKER_FUNCTIONAL_TEST_CLOUD_CONFIG_FILE environment '
            'variable.'
        )

    # ie storage-drivers.rackspace
    config_section = environ.get(
        'FLOCKER_FUNCTIONAL_TEST_CLOUD_CONFIG_SECTION',
    )
    if config_section is None:
        raise SkipTest(
            'Supply the section of the config file '
            'containing the configuration for the driver under test '
            'with the FLOCKER_FUNCTIONAL_TEST_CLOUD_CONFIG_SECTION '
            'environment variable.'
        )

    with open(config_file_path) as config_file:
        config = yaml.safe_load(config_file.read())

    section = None
    for section in config_section.split('.'):
        config = config.get(section)

    if config is None:
        raise InvalidConfig(
            "The requested section "
            "was not found in the configuration file. "
            "Section: %s, "
            "Configuration File: %s" % (config_section, config_file_path)
        )

    # XXX A hack to work around the fact that the sub-sections of
    # storage-drivers in acceptance.yml do not all have a ``backend`` key.
    if "backend" not in config:
        config["backend"] = section

    return config


def get_openstack_region_for_test():
    """
    Return a default Openstack region for testing.

    The default region comes from an environment variable.  Keystone
    uses case-sensitive regions, so ensure region is uppercase.
    """
    region = environ.get('FLOCKER_FUNCTIONAL_TEST_OPENSTACK_REGION')
    if region is not None:
        region = region.upper()
    return region


def _openstack(cluster_id, config):
    """
    Create an IBlockDeviceAPI provider configured to use the Openstack
    region where the server that is running this code is running.

    :param config: Any additional configuration (possibly provider-specific)
        necessary to authenticate a keystone session.
    :return: A CinderBlockDeviceAPI instance.
    """
    configured_region = config.pop('region', None)
    # XXX Our build server sets a static region environment variable so this
    # seems pretty pointless. I'll fix it in a followup.
    override_region = get_openstack_region_for_test()
    region = override_region or configured_region
    return cinder_from_configuration(region, cluster_id, **config)


def get_ec2_client_for_test(config):
    """
    Get a simple EC2 client, configured for the test region.
    """

    # We just get the credentials from the config file.
    # We ignore the region specified in acceptance test configuration,
    # and instead get the region from the zone of the host.
    zone = environ['FLOCKER_FUNCTIONAL_TEST_AWS_AVAILABILITY_ZONE']
    # The region is the zone, without the trailing [abc].
    region = zone[:-1]
    return ec2_client(
        region=region,
        zone=zone,
        access_key_id=config['access_key_id'],
        secret_access_key=config['secret_access_key']
    )


def _aws(cluster_id, config):
    """
    Create an IBlockDeviceAPI provider configured to use the AWS EC2
    region where the server that is running this code is running.

    :param config: Any additional configuration (possibly provider-specific)
        necessary to authenticate an EC2 session.
    :return: An EBSBlockDeviceAPI instance.
    """
    return EBSBlockDeviceAPI(
        cluster_id=cluster_id,
        ec2_client=get_ec2_client_for_test(config),
    )


def _gce(cluster_id, config):
    """
    Create an IBlockDeviceAPI provider configured to use the GCE
    persistent device region where the server that is running this
    code is running. This function assumes it's running on a GCE node.

    :param cluster_id: The flocker cluster id.
    :param config: Unused.
    :return: A GCEBlockDeviceAPI instance.
    """
    return gce_from_configuration(cluster_id=cluster_id)


# Map provider labels to IBlockDeviceAPI factory.
_BLOCKDEVICE_TYPES = {
    Providers.OPENSTACK: _openstack,
    Providers.AWS: _aws,
    Providers.GCE: _gce,
}


def get_blockdeviceapi_with_cleanup(test_case):
    """
    Instantiate an ``IBlockDeviceAPI`` implementation configured to work in the
    current environment.  Arrange for all volumes created by it to be cleaned
    up at the end of the current test run.

    :param TestCase test_case: The running test.
    :raises: ``SkipTest`` if either:
        1) A ``FLOCKER_FUNCTIONAL_TEST_CLOUD_CONFIG_FILE``
        was not set and the default config file could not be read, or,
        2) ``FLOCKER_FUNCTIONAL_TEST`` environment variable was unset.

    :return: The new ``IBlockDeviceAPI`` provider.
    """
    try:
        api = get_blockdeviceapi()
    except InvalidConfig as e:
        raise SkipTest(str(e))
    test_case.addCleanup(detach_destroy_volumes, api)
    return api


DEVICE_ALLOCATION_UNITS = {
    # Our redhat-openstack test platform uses a ScaleIO backend which
    # allocates devices in 8GiB intervals
    'redhat-openstack': GiB(8),
}


def get_device_allocation_unit():
    """
    Return a provider specific device allocation unit.

    This is mostly OpenStack / Cinder specific and represents the
    interval that will be used by Cinder storage provider i.e
    You ask Cinder for a 1GiB or 7GiB volume.
    The Cinder driver creates an 8GiB block device.
    The operating system sees an 8GiB device when it is attached.
    Cinder API reports a 1GiB or 7GiB volume.

    :returns: An ``int`` allocation size in bytes for a
        particular platform. Default to ``None``.
    """
    cloud_provider = environ.get('FLOCKER_FUNCTIONAL_TEST_CLOUD_PROVIDER')
    if cloud_provider is not None:
        device_allocation_unit = DEVICE_ALLOCATION_UNITS.get(cloud_provider)
        if device_allocation_unit is not None:
            return int(device_allocation_unit.to_Byte().value)


MINIMUM_ALLOCATABLE_SIZES = {
    'rackspace': RACKSPACE_MINIMUM_VOLUME_SIZE,
    'devstack-openstack': GiB(1),
    'redhat-openstack': GiB(1),
    'aws': GiB(1),
    'gce': GiB(10),
}


def get_minimum_allocatable_size():
    """
    Return a provider specific minimum_allocatable_size.

    :returns: An ``int`` minimum_allocatable_size in bytes for a
        particular platform. Default to ``1``.
    """
    cloud_provider = environ.get('FLOCKER_FUNCTIONAL_TEST_CLOUD_PROVIDER')
    if cloud_provider is None:
        return 1
    else:
        return int(MINIMUM_ALLOCATABLE_SIZES[cloud_provider].to_Byte().value)


def require_backend(required_backend):
    config = get_blockdevice_config()
    configured_backend = config.pop('backend')
    return skipUnless(
        configured_backend == required_backend,
        'The backend in the supplied configuration '
        'is not suitable for this test. '
        'Found: {!r}. Required: {!r}.'.format(
            configured_backend, required_backend
        )
    )
