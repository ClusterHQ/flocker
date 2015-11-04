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

from twisted.python.runtime import platform
from twisted.python.filepath import FilePath
from twisted.trial.unittest import SynchronousTestCase, SkipTest

from eliot import start_action, write_traceback, Message

from ....testtools import (
    random_name,
)

from ..blockdevice import (
    BlockDeviceDeployer,
    _SyncToThreadedAsyncAPIAdapter,
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
