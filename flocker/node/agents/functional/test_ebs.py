# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Functional tests for ``flocker.node.agents.ebs`` using an EC2 cluster.

"""

from uuid import uuid4

from bitmath import Byte

from boto.exception import EC2ResponseError

from twisted.trial.unittest import SkipTest
from eliot.testing import LoggedMessage, capture_logging

from ..ebs import (
    _wait_for_volume, BOTO_EC2RESPONSE_ERROR,
)

from .._logging import (
    AWS_CODE, AWS_MESSAGE, AWS_REQUEST_ID, BOTO_LOG_HEADER,
)
from ..test.test_blockdevice import make_iblockdeviceapi_tests

from ..test.blockdevicefactory import (
    InvalidConfig, ProviderType, get_blockdeviceapi_args,
    get_blockdeviceapi_with_cleanup, get_device_allocation_unit,
    get_minimum_allocatable_size,
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
            minimum_allocatable_size=get_minimum_allocatable_size(),
            device_allocation_unit=get_device_allocation_unit(),
            unknown_blockdevice_id_factory=lambda test: u"vol-00000000",
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
            int(Byte(self.minimum_allocatable_size).to_GiB().value),
            ec2_client.zone)
        self.addCleanup(ec2_client.connection.delete_volume,
                        requested_volume.id)

        _wait_for_volume(requested_volume,
                         u'',
                         u'creating',
                         u'available')

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
            size=self.minimum_allocatable_size,
        )
        self.assert_foreign_volume(flocker_volume)

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
        self.assertRaises(
            EC2ResponseError,
            self.api.create_volume,
            dataset_id=uuid4(),
            size=self.minimum_allocatable_size,
        )

        # Validate decorated method for exception logging
        # actually logged to ``Eliot`` logger.
        expected_message_keys = {AWS_CODE.key, AWS_MESSAGE.key,
                                 AWS_REQUEST_ID.key}
        for logged in LoggedMessage.of_type(logger.messages,
                                            BOTO_EC2RESPONSE_ERROR,):
            key_subset = set(key for key in expected_message_keys
                             if key in logged.message.keys())
            self.assertEqual(expected_message_keys, key_subset)

    @capture_logging(None)
    def test_boto_request_logging(self, logger):
        """
        Boto is configured to send log events to Eliot when it makes an AWS API
        request.
        """
        self.api.list_volumes()

        messages = list(
            message
            for message
            in logger.messages
            if message.get("message_type") == BOTO_LOG_HEADER
        )
        self.assertNotEqual(
            [], messages,
            "Didn't find Boto messages in logged messages {}".format(
                messages
            )
        )

    def test_next_device_in_use(self):
        """
        ``_next_device`` skips devices indicated as being in use.

        Ideally we'd have a test for this using the public API, but this
        only occurs if we hit eventually consistent ignorance in the AWS
        servers so it's hard to trigger deterministically.
        """
        result = self.api._next_device(self.api.compute_instance_id(), [],
                                       {u"/dev/sdf"})
        self.assertEqual(result, u"/dev/sdg")
