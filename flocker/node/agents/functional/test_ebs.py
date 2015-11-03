# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Functional tests for ``flocker.node.agents.ebs`` using an EC2 cluster.

"""

import time
from uuid import uuid4
from bitmath import Byte, GiB

from boto.ec2.volume import (
    Volume as EbsVolume, AttachmentSet
)
from boto.exception import EC2ResponseError

from twisted.python.constants import Names, NamedConstant
from twisted.trial.unittest import SkipTest, TestCase
from eliot.testing import LoggedMessage, capture_logging, assertHasMessage

from ..blockdevice import MandatoryProfiles

from ..ebs import (
    _wait_for_volume_state_change, BOTO_EC2RESPONSE_ERROR,
    VolumeOperations, VolumeStateTable, VolumeStates,
    TimeoutException, _should_finish, UnexpectedStateException,
    EBSMandatoryProfileAttributes
)

from .._logging import (
    AWS_CODE, AWS_MESSAGE, AWS_REQUEST_ID, BOTO_LOG_HEADER,
    CREATE_VOLUME_FAILURE
)
from ..test.test_blockdevice import (
    make_iblockdeviceapi_tests, make_iprofiledblockdeviceapi_tests
)

from ..test.blockdevicefactory import (
    InvalidConfig, ProviderType, get_blockdevice_config,
    get_blockdeviceapi_with_cleanup, get_device_allocation_unit,
    get_minimum_allocatable_size, get_ec2_client_for_test,
)

TIMEOUT = 5


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
        ``list_volumes`` lists only those volumes
        belonging to the current Flocker cluster.
        """
        try:
            config = get_blockdevice_config(ProviderType.aws)
        except InvalidConfig as e:
            raise SkipTest(str(e))
        ec2_client = get_ec2_client_for_test(config)
        requested_volume = ec2_client.connection.create_volume(
            int(Byte(self.minimum_allocatable_size).to_GiB().value),
            ec2_client.zone)
        self.addCleanup(ec2_client.connection.delete_volume,
                        requested_volume.id)

        _wait_for_volume_state_change(VolumeOperations.CREATE,
                                      requested_volume)

        self.assertEqual(self.api.list_volumes(), [])

    def test_foreign_cluster_volume(self):
        """
        ``list_volumes`` excludes volumes belonging to
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

    def test_naming(self):
        """
        Newly created volumes get the "Name" tag set to a human-readable name.
        """
        try:
            config = get_blockdevice_config(ProviderType.aws)
        except InvalidConfig as e:
            raise SkipTest(str(e))

        dataset_id = uuid4()
        flocker_volume = self.api.create_volume(
            dataset_id=dataset_id,
            size=self.minimum_allocatable_size,
        )
        ec2_client = get_ec2_client_for_test(config)
        name = ec2_client.connection.get_all_volumes(
            volume_ids=[flocker_volume.blockdevice_id])[0].tags[u"Name"]
        self.assertEqual(name, u"flocker-{}".format(dataset_id))

    @capture_logging(lambda self, logger: None)
    def test_boto_ec2response_error(self, logger):
        """
        1. Invalid parameters to Boto's EBS API calls
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

    def test_create_volume_gold_profile(self):
        """
        Requesting ``gold`` profile during volume creation honors
        ``gold`` attributes.
        """
        self._assert_create_volume_with_mandatory_profile(
            MandatoryProfiles.GOLD)

    @capture_logging(assertHasMessage, CREATE_VOLUME_FAILURE)
    def test_create_volume_violate_requested_profile(self, logger):
        """
        Volume creation request that cannot satisfy attributes of requested
        profile makes a second (successful) attempt to create the volume with
        default profile.
        """
        self._assert_create_volume_with_mandatory_profile(
            MandatoryProfiles.GOLD, created_profile=MandatoryProfiles.DEFAULT,
            size_GiB=1)

    def test_create_too_large_volume_with_profile(self):
        """
        Create a volume so large that none of the ``MandatoryProfiles``
        can be assigned to it.
        """
        self.assertRaises(EC2ResponseError,
                          self._assert_create_volume_with_mandatory_profile,
                          MandatoryProfiles.GOLD,
                          size_GiB=1024*1024)

    def test_create_volume_silver_profile(self):
        """
        Requesting ``silver`` profile during volume creation honors
        ``silver`` attributes.
        """
        self._assert_create_volume_with_mandatory_profile(
            MandatoryProfiles.SILVER)

    def test_create_too_large_volume_silver_profile(self):
        """
        Too large volume (> 16TiB) for ``silver`` profile.
        """
        self.assertRaises(EC2ResponseError,
                          self._assert_create_volume_with_mandatory_profile,
                          MandatoryProfiles.SILVER,
                          size_GiB=1024*1024)

    def test_create_volume_bronze_profile(self):
        """
        Requesting ``bronze`` profile during volume creation honors
        ``bronze`` attributes.
        """
        self._assert_create_volume_with_mandatory_profile(
            MandatoryProfiles.BRONZE)

    def _assert_create_volume_with_mandatory_profile(self, profile,
                                                     created_profile=None,
                                                     size_GiB=4):
        """
        Volume created with given profile has the attributes
        expected from the profile.

        :param ValueConstant profile: Name of profile to use for creation.
        :param ValueConstant created_profile: Name of the profile volume is
            expected to be created with.
        :param int size_GiB: Size of volume to be created.
        """
        if created_profile is None:
            created_profile = profile
        volume1 = self.api.create_volume_with_profile(
            dataset_id=uuid4(),
            size=self.minimum_allocatable_size * size_GiB,
            profile_name=profile.value)

        cannonical_profile = MandatoryProfiles.lookupByValue(
            created_profile.value)
        A = EBSMandatoryProfileAttributes.lookupByName(
            cannonical_profile.name).value
        ebs_volume = self.api._get_ebs_volume(volume1.blockdevice_id)
        self.assertEqual(ebs_volume.type, A.volume_type.value)
        requested_iops = A.requested_iops(ebs_volume.size)
        self.assertEqual(ebs_volume.iops if requested_iops is not None
                         else None, requested_iops)


class EBSProfiledBlockDeviceAPIInterfaceTests(
        make_iprofiledblockdeviceapi_tests(
            profiled_blockdevice_api_factory=ebsblockdeviceapi_for_test,
            dataset_size=GiB(4).to_Byte().value
        )
):
    """
    Interface adherence tests for ``IProfiledBlockDeviceAPI``.
    """
    pass


class VolumeStateTransitionTests(TestCase):
    """
    Tests for volume state operations and resulting volume state changes.
    """

    class VolumeEndStateTypes(Names):
        """
        Types of volume states to simulate.
        """
        ERROR_STATE = NamedConstant()
        TRANSIT_STATE = NamedConstant()
        DESTINATION_STATE = NamedConstant()

    class VolumeAttachDataTypes(Names):
        """
        Types of volume's attach data states to simulate.
        """
        MISSING_ATTACH_DATA = NamedConstant()
        MISSING_INSTANCE_ID = NamedConstant()
        MISSING_DEVICE = NamedConstant()
        ATTACH_SUCCESS = NamedConstant()
        DETACH_SUCCESS = NamedConstant()

    V = VolumeOperations
    S = VolumeEndStateTypes
    A = VolumeAttachDataTypes

    def _create_template_ebs_volume(self, operation):
        """
        Helper function to create template EBS volume to work on.

        :param NamedConstant operation: Intended use of created template.
            A value from ``VolumeOperations``.

        :returns: Suitable volume in the right start state for input operation.
        :rtype: boto.ec2.volume.Volume
        """
        volume = EbsVolume()

        # Irrelevant volume attributes.
        volume.id = u'vol-9c48a689'
        volume.create_time = u'2015-07-14T22:46:00.447Z'
        volume.size = 1
        volume.snapshot_id = ''
        volume.zone = u'us-west-2b'
        volume.type = u'standard'

        volume_state_table = VolumeStateTable()
        state_flow = volume_state_table.table[operation]
        start_state = state_flow.start_state.value

        # Interesting volume attribute.
        volume.status = start_state

        return volume

    def _pick_end_state(self, operation, state_type):
        """
        Helper function to pick a desired volume state for given input
        operation.

        :param NamedConstant operation: Volume operation to pick a
            state for. A value from ``VolumeOperations``.
        :param NamedConstant state_type: Volume state type request.

        :returns: A state from ``VolumeStates`` that will not be part of
            a volume's states resulting from input operation.
        :rtype: ValueConstant
        """
        volume_state_table = VolumeStateTable()
        state_flow = volume_state_table.table[operation]

        if state_type == self.S.ERROR_STATE:
            valid_states = set([state_flow.start_state,
                                state_flow.transient_state,
                                state_flow.end_state])

            err_states = set(VolumeStates._enumerants.values()) - valid_states
            err_state = err_states.pop()
            return err_state.value
        elif state_type == self.S.TRANSIT_STATE:
            return state_flow.transient_state.value
        elif state_type == self.S.DESTINATION_STATE:
            return state_flow.end_state.value

    def _pick_attach_data(self, attach_type):
        """
        Helper function to create desired volume attach data.

        :param NamedConstant attach_type: Type of attach data to create.

        :returns: Volume attachment set that conforms to requested attach type.
        :rtype: AttachmentSet
        """
        if attach_type == self.A.MISSING_ATTACH_DATA:
            return None
        elif attach_type == self.A.MISSING_INSTANCE_ID:
            attach_data = AttachmentSet()
            attach_data.device = u'/dev/sdf'
            attach_data.instance_id = ''
            return attach_data
        elif attach_type == self.A.MISSING_DEVICE:
            attach_data = AttachmentSet()
            attach_data.device = ''
            attach_data.instance_id = u'i-xyz'
            return attach_data
        elif attach_type == self.A.ATTACH_SUCCESS:
            attach_data = AttachmentSet()
            attach_data.device = u'/dev/sdf'
            attach_data.instance_id = u'i-xyz'
            return attach_data
        elif attach_type == self.A.DETACH_SUCCESS:
            return None

    def _custom_update(self, operation, state_type,
                       attach_data=A.MISSING_ATTACH_DATA):
        """
        Create a custom update function for a volume.
        """
        def update(volume):
            """
            Transition volume to desired end state and attach data.

            :param boto.ec2.volume.Volume volume: Volume to move to
                invalid state.
            """
            volume.status = self._pick_end_state(operation, state_type)
            volume.attach_data = self._pick_attach_data(attach_data)
        return update

    def _assert_unexpected_state_exception(self, operation,
                                           volume_end_state_type,
                                           attach_type=A.MISSING_ATTACH_DATA):
        """
        Assert that configured volume state change for given testcase indicates
        incomplete operation execution.
        """
        volume = self._create_template_ebs_volume(operation)
        update = self._custom_update(operation, volume_end_state_type,
                                     attach_type)
        start_time = time.time()
        self.assertRaises(UnexpectedStateException, _should_finish,
                          operation, volume, update, start_time, TIMEOUT)

    def _assert_fail(self, operation, volume_end_state_type,
                     attach_data_type=A.MISSING_ATTACH_DATA):
        """
        Assert that configured volume state change for given testcase indicates
        incomplete operation execution.
        """
        volume = self._create_template_ebs_volume(operation)
        update = self._custom_update(operation, volume_end_state_type,
                                     attach_data_type)
        start_time = time.time()
        finish_result = _should_finish(operation, volume, update, start_time)
        self.assertEqual(False, finish_result)

    def _assert_timeout(self, operation, testcase,
                        attach_data_type=A.MISSING_ATTACH_DATA):
        """
        Helper function to validate that ``TimeoutException`` is raised as
        a result of performing input operation for given testcase on a volume.
        """
        volume = self._create_template_ebs_volume(operation)
        update = self._custom_update(operation, testcase, attach_data_type)

        start_time = time.time()
        time.sleep(TIMEOUT)
        self.assertRaises(TimeoutException, _should_finish,
                          operation, volume, update, start_time, TIMEOUT)

    def _process_volume(self, operation, testcase,
                        attach_data_type=A.ATTACH_SUCCESS):
        """
        Helper function to validate that performing given operation for given
        testcase on a volume succeeds.
        """
        volume = self._create_template_ebs_volume(operation)
        _wait_for_volume_state_change(operation, volume,
                                      self._custom_update(operation, testcase,
                                                          attach_data_type),
                                      TIMEOUT)
        return volume

    def test_create_invalid_state(self):
        """
        Assert that error volume state during creation raises
        ``UnexpectedStateException``.
        """
        self._assert_unexpected_state_exception(self.V.CREATE,
                                                self.S.ERROR_STATE)

    def test_destroy_invalid_state(self):
        """
        Assert that error volume state during destroy raises
        ``UnexpectedStateException``.
        """
        self._assert_unexpected_state_exception(self.V.DESTROY,
                                                self.S.ERROR_STATE)

    def test_attach_invalid_state(self):
        """
        Assert that error volume state during attach raises
        ``UnexpectedStateException``.
        """
        self._assert_unexpected_state_exception(self.V.ATTACH,
                                                self.S.ERROR_STATE)

    def test_detach_invalid_state(self):
        """
        Assert that error volume state during detach raises
        ``UnexpectedStateException``.
        """
        self._assert_unexpected_state_exception(self.V.DETACH,
                                                self.S.ERROR_STATE)

    def test_stuck_create(self):
        """
        Assert that stuck create state indicates operation in progress.
        """
        self._assert_fail(self.V.CREATE, self.S.TRANSIT_STATE)

    def test_stuck_destroy(self):
        """
        Assert that stuck destroy state indicates operation in progress.
        """
        self._assert_fail(self.V.DESTROY, self.S.TRANSIT_STATE)

    def test_stuck_attach(self):
        """
        Assert that stuck attach state indicates operation in progress.
        """
        self._assert_fail(self.V.ATTACH, self.S.TRANSIT_STATE)

    def test_stuck_detach(self):
        """
        Assert that stuck detach state indicates operation in progress.
        """
        self._assert_fail(self.V.DETACH, self.S.TRANSIT_STATE)

    def test_attach_missing_attach_data(self):
        """
        Assert that missing attach data indicates attach in progress.
        """
        self._assert_fail(self.V.ATTACH, self.S.DESTINATION_STATE)

    def test_attach_missing_instance_id(self):
        """
        Assert that missing attach instance id indicates attach in progress.
        """
        self._assert_fail(self.V.ATTACH, self.S.DESTINATION_STATE,
                          self.A.MISSING_INSTANCE_ID)

    def test_attach_missing_device(self):
        """
        Assert that missing attached device name indicates attach in progress.
        """
        self._assert_fail(self.V.ATTACH, self.S.DESTINATION_STATE,
                          self.A.MISSING_DEVICE)

    def test_timeout(self):
        """
        Assert that ``TimeoutException`` is thrown if volume state transition
        takes longer than configured timeout.
        """
        self._assert_timeout(self.V.ATTACH, self.S.DESTINATION_STATE)

    def test_create_success(self):
        """
        Assert that successful volume creation leads to valid volume end state.
        """
        volume = self._process_volume(self.V.CREATE, self.S.DESTINATION_STATE)
        self.assertEqual(volume.status, u'available')

    def test_destroy_success(self):
        """
        Assert that successful volume destruction leads to valid end state.
        """
        volume = self._process_volume(self.V.DESTROY, self.S.DESTINATION_STATE)
        self.assertEquals(volume.status, u'')

    def test_attach_sucess(self):
        """
        Test if successful attach volume operation leads to expected state.
        """
        volume = self._process_volume(self.V.ATTACH, self.S.DESTINATION_STATE)
        self.assertEqual([volume.status, volume.attach_data.device,
                          volume.attach_data.instance_id],
                         [u'in-use', u'/dev/sdf', u'i-xyz'])

    def test_detach_success(self):
        """
        Test if successful detach volume operation leads to expected state.
        """
        volume = self._process_volume(self.V.DETACH, self.S.DESTINATION_STATE,
                                      self.A.DETACH_SUCCESS)
        self.assertEqual(volume.status, u'available')
