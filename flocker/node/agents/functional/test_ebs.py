# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Functional tests for ``flocker.node.agents.ebs`` using an EC2 cluster.

"""

from uuid import uuid4

from bitmath import Byte

from twisted.trial.unittest import SkipTest

from ..ebs import (_wait_for_volume, ATTACHED_DEVICE_LABEL, UnattachedVolume)
from ..test.test_blockdevice import (
    make_iblockdeviceapi_tests,
    REALISTIC_BLOCKDEVICE_SIZE
)

from ..test.blockdevicefactory import (
    InvalidConfig, ProviderType, get_blockdeviceapi_args,
    get_blockdeviceapi_with_cleanup, get_over_allocation,
)


def ebsblockdeviceapi_for_test(test_case):
    """
    Create an ``EBSBlockDeviceAPI`` for use by tests.
    """
    return get_blockdeviceapi_with_cleanup(test_case, ProviderType.aws)


class EBSBlockDeviceAPIInterfaceTests(
        make_iblockdeviceapi_tests(
            blockdevice_api_factory=(
                lambda test_case: ebsblockdeviceapi_for_test(
                    test_case=test_case,
                )
            ),
            over_allocation=get_over_allocation(),
        )
):

    """
    Interface adherence Tests for ``EBSBlockDeviceAPI``.
    """
    # We haven't implemented resize functionality yet.
    def test_resize_destroyed_volume(self):
        raise SkipTest("Resize not implemented on AWS - FLOC-1985")

    def test_resize_unknown_volume(self):
        raise SkipTest("Resize not implemented on AWS - FLOC-1985")

    def test_resize_volume_listed(self):
        raise SkipTest("Resize not implemented on AWS - FLOC-1985")

    def test_foreign_volume(self):
        """
        Test that ``list_volumes`` lists only those volumes
        belonging to the current Flocker cluster.
        """
        try:
            cls, kwargs = get_blockdeviceapi_args(ProviderType.aws)
        except InvalidConfig as e:
            raise SkipTest(str(e))
        ec2_client = kwargs["ec2_client"]
        requested_volume = ec2_client.connection.create_volume(
            int(Byte(REALISTIC_BLOCKDEVICE_SIZE).to_GiB().value),
            ec2_client.zone)
        self.addCleanup(ec2_client.connection.delete_volume,
                        requested_volume.id)

        _wait_for_volume(requested_volume)

        self.assertEqual(self.api.list_volumes(), [])

    def test_foreign_cluster_volume(self):
        """
        Test that list_volumes() excludes volumes belonging to
        other Flocker clusters.
        """
        blockdevice_api2 = ebsblockdeviceapi_for_test(
            test_case=self,
        )
        flocker_volume = blockdevice_api2.create_volume(
            dataset_id=uuid4(),
            size=REALISTIC_BLOCKDEVICE_SIZE,
        )
        self.assert_foreign_volume(flocker_volume)

    def test_attached_volume_missing_device_tag(self):
        """
        Test that missing ATTACHED_DEVICE_LABEL on an EBS
        volume causes `UnattacheVolume` while attempting
        `get_device_path()`.
        """
        volume = self.api.create_volume(
            dataset_id=uuid4(),
            size=REALISTIC_BLOCKDEVICE_SIZE,
        )
        self.api.attach_volume(
            volume.blockdevice_id,
            attach_to=self.this_node,
        )

        self.api.connection.delete_tags([volume.blockdevice_id],
                                        [ATTACHED_DEVICE_LABEL])

        self.assertRaises(UnattachedVolume, self.api.get_device_path,
                          volume.blockdevice_id)
