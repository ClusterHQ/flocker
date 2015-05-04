# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Functional tests for ``flocker.node.agents.ebs`` using an EC2 cluster.

"""

from uuid import uuid4

from bitmath import Byte

from ..ebs import EBSBlockDeviceAPI, _wait_for_volume
from ..testtools import ec2_client_from_environment
from ....testtools import skip_except
from ..test.test_blockdevice import (
    make_iblockdeviceapi_tests, detach_destroy_volumes,
    REALISTIC_BLOCKDEVICE_SIZE
)


def ebsblockdeviceapi_for_test(test_case, cluster_id):
    """
    Create an ``EBSBlockDeviceAPI`` for use by tests.

    :param string cluster_id: Flocker cluster id to be used
        by the current set of tests.
    """
    ebs_blockdevice_api = EBSBlockDeviceAPI(
        ec2_client=ec2_client_from_environment(),
        cluster_id=cluster_id
        )

    test_case.addCleanup(detach_destroy_volumes, ebs_blockdevice_api)
    return ebs_blockdevice_api


# ``EBSBlockDeviceAPI`` only implements the ``create``, ``list``,
# and ``destroy`` parts of ``IBlockDeviceAPI``.
@skip_except(
    supported_tests=[
        'test_interface',
        'test_created_is_listed',
        'test_created_volume_attributes',
        'test_list_volume_empty',
        'test_listed_volume_attributes',
        'test_foreign_cluster_volume',
        'test_foreign_volume',
        'test_destroy_unknown_volume',
        'test_destroy_volume',
        'test_destroy_destroyed_volume',
    ]
)
class EBSBlockDeviceAPIInterfaceTests(
        make_iblockdeviceapi_tests(
            blockdevice_api_factory=(
                lambda test_case: ebsblockdeviceapi_for_test(
                    test_case=test_case,
                    cluster_id=uuid4()
                )
            )
        )
):

    """
    Interface adherence Tests for ``EBSBlockDeviceAPI``.
    """
    def test_foreign_volume(self):
        """
        Test that ``list_volumes`` lists only those volumes
        belonging to the current Flocker cluster.
        """
        ec2_client = ec2_client_from_environment()
        requested_volume = ec2_client.connection.create_volume(
            int(Byte(REALISTIC_BLOCKDEVICE_SIZE).to_GB().value),
            ec2_client.zone)

        _wait_for_volume(requested_volume)

        self.addCleanup(ec2_client.connection.delete_volume,
                        requested_volume.id)
        self.assertEqual(self.api.list_volumes(), [])

    def test_foreign_cluster_volume(self):
        """
        Test that list_volumes() excludes volumes belonging to
        other Flocker clusters.
        """
        blockdevice_api2 = ebsblockdeviceapi_for_test(
            test_case=self,
            cluster_id=uuid4(),
            )
        flocker_volume = blockdevice_api2.create_volume(
            dataset_id=uuid4(),
            size=REALISTIC_BLOCKDEVICE_SIZE,
        )

        self.addCleanup(blockdevice_api2.destroy_volume,
                        flocker_volume.blockdevice_id)
        self.assert_foreign_volume(flocker_volume)
