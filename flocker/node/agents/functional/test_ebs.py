# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Functional tests for ``flocker.node.agents.ebs`` using an EC2 cluster.

"""

from uuid import uuid4

from bitmath import Byte

from boto.exception import EC2ResponseError

from twisted.trial.unittest import SkipTest
from eliot.testing import LoggedMessage, capture_logging

from ..ebs import (_wait_for_volume, ATTACHED_DEVICE_LABEL,
                   BOTO_EC2RESPONSE_ERROR, UnattachedVolume,
                   CODE, MESSAGE, REQUEST_ID)
from ....testtools import skip_except
from ..test.test_blockdevice import (
    make_iblockdeviceapi_tests,
    REALISTIC_BLOCKDEVICE_SIZE
)

from ..test.blockdevicefactory import (
    InvalidConfig, ProviderType, get_blockdeviceapi_args,
    get_blockdeviceapi_with_cleanup,
)


def ebsblockdeviceapi_for_test(test_case):
    """
    Create an ``EBSBlockDeviceAPI`` for use by tests.
    """
    return get_blockdeviceapi_with_cleanup(test_case, ProviderType.aws)


# ``EBSBlockDeviceAPI`` only implements the ``create``, ``list``,
# and ``destroy`` parts of ``IBlockDeviceAPI``.
@skip_except(
    supported_tests=[
        'test_attach_attached_volume',
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
        'test_attach_attached_volume',
        'test_attach_unknown_volume',
        'test_attach_elsewhere_attached_volume',
        'test_attach_unattached_volume',
        'test_attach_destroyed_volume',
        'test_attached_volume_listed',
        'test_list_attached_and_unattached',
        'test_detach_detached_volume',
        'test_detach_unknown_volume',
        'test_reattach_detached_volume',
        'test_multiple_volumes_attached_to_host',
        'test_compute_instance_id_nonempty',
        'test_compute_instance_id_unicode',
        'test_get_device_path_device',
        'test_get_device_path_device_repeatable_results',
        'test_get_device_path_unattached_volume',
        'test_get_device_path_unknown_volume',
        'test_detach_volume',
        'test_attach_volume_validate_size',
        'test_attached_volume_missing_device_tag',
        'test_boto_ec2response_error',
    ]
)
class EBSBlockDeviceAPIInterfaceTests(
        make_iblockdeviceapi_tests(
            blockdevice_api_factory=(
                lambda test_case: ebsblockdeviceapi_for_test(
                    test_case=test_case,
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

    @capture_logging(lambda self, logger: None)
    def test_boto_ec2response_error(self, logger):
        """
        1. Test that invalid parameters to Boto's EBS API calls
        raise the right exception after logging to Eliot.
        2. Verify Eliot log output for expected message fields
        from logging decorator for boto.exception.EC2Exception
        originating from boto.ec2.connection.EC2Connection.
        """
        # Test 1: Create volume with size 0.
        # Raises: EC2ResponseError
        self.assertRaises(EC2ResponseError, self.api.create_volume,
                          dataset_id=uuid4(), size=0,)

        # Test 2: Set EC2 connection zone to an invalid string.
        # Raises: EC2ResponseError
        self.api.zone = u'invalid_zone'
        self.assertRaises(EC2ResponseError, self.api.create_volume,
                          dataset_id=uuid4(), size=REALISTIC_BLOCKDEVICE_SIZE,)

        # Validate decorated method for exception logging
        # actually logged to ``Eliot`` logger.
        expected_message_keys = {CODE.key, MESSAGE.key, REQUEST_ID.key}
        for logged in LoggedMessage.of_type(logger.messages,
                                            BOTO_EC2RESPONSE_ERROR,):
            key_subset = set(key for key in expected_message_keys
                             if key in logged.message.keys())
            self.assertEqual(expected_message_keys, key_subset)
