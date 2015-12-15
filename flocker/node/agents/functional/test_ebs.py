# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Functional tests for ``flocker.node.agents.ebs`` using an EC2 cluster.

"""

import time
from uuid import uuid4
from bitmath import Byte, GiB

from botocore.exceptions import ClientError

from twisted.python.constants import Names, NamedConstant
from twisted.trial.unittest import SkipTest, TestCase
from eliot.testing import LoggedAction, capture_logging, assertHasMessage

from ..blockdevice import MandatoryProfiles

from ..ebs import (
    _wait_for_volume_state_change,
    VolumeOperations, VolumeStateTable, VolumeStates,
    TimeoutException, _should_finish, UnexpectedStateException,
    EBSMandatoryProfileAttributes, _get_volume_tag,
)
from ....testtools import flaky

from .._logging import (
    AWS_CODE, AWS_MESSAGE, AWS_REQUEST_ID, BOTO_LOG_HEADER,
    CREATE_VOLUME_FAILURE, AWS_ACTION,
)
from ..test.test_blockdevice import (
    make_iblockdeviceapi_tests, make_iprofiledblockdeviceapi_tests,
    make_icloudapi_tests,
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
        meta_client = ec2_client.connection.meta.client
        requested_volume = meta_client.create_volume(
            Size=int(Byte(self.minimum_allocatable_size).to_GiB().value),
            AvailabilityZone=ec2_client.zone)
        created_volume = ec2_client.connection.Volume(
            requested_volume['VolumeId'])
        self.addCleanup(created_volume.delete)

        _wait_for_volume_state_change(VolumeOperations.CREATE,
                                      created_volume)

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
        volume = ec2_client.connection.Volume(flocker_volume.blockdevice_id)
        name = _get_volume_tag(volume, u"Name")
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
        # Raises: ClientError
        self.assertRaises(ClientError, self.api.create_volume,
                          dataset_id=uuid4(), size=0,)

        # Test 2: Set EC2 connection zone to an invalid string.
        # Raises: ClientError
        self.api.zone = u'invalid_zone'
        self.assertRaises(
            ClientError,
            self.api.create_volume,
            dataset_id=uuid4(),
            size=self.minimum_allocatable_size,
        )

        # Validate decorated method for exception logging
        # actually logged to ``Eliot`` logger.
        expected_message_keys = {AWS_CODE.key, AWS_MESSAGE.key,
                                 AWS_REQUEST_ID.key}
        for logged in LoggedAction.of_type(logger.messages, AWS_ACTION,):
            key_subset = set(key for key in expected_message_keys
                             if key in logged.end_message.keys())
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

    def test_next_device_in_use_end(self):
        """
        ``_next_device`` returns ``None`` if all devices are in use.
        """
        devices_in_use = {
            u'/dev/sd{}'.format(d)
            for d in u'fghijklmnop'
        }
        result = self.api._next_device(
            self.api.compute_instance_id(), [], devices_in_use
        )
        self.assertIs(result, None)

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
        self.assertRaises(ClientError,
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
        self.assertRaises(ClientError,
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
        self.assertEqual(ebs_volume.volume_type, A.volume_type.value)
        requested_iops = A.requested_iops(ebs_volume.size)
        self.assertEqual(ebs_volume.iops if requested_iops is not None
                         else None, requested_iops)

    @flaky(u'FLOC-2302')
    def test_listed_volume_attributes(self):
        return super(
            EBSBlockDeviceAPIInterfaceTests,
            self).test_listed_volume_attributes()

    @flaky(u'FLOC-2672')
    def test_multiple_volumes_attached_to_host(self):
        return super(
            EBSBlockDeviceAPIInterfaceTests,
            self).test_multiple_volumes_attached_to_host()

    @flaky(u'FLOC-3236')
    def test_detach_volume(self):
        return super(
            EBSBlockDeviceAPIInterfaceTests, self).test_detach_volume()


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


class VolumeStub(object):
    """
    Stub object to represent properties found on the immutable
    `boto3.resources.factory.ec2.Volume`. This allows a ``Volume``
    with properties to be compared to expected values.
    """
    def __init__(self, **kwargs):
        self._volume_attributes = dict(
            id=None, create_time=None, tags=None, attachments=None,
            size=None, snapshot_id=None, zone=None, volume_type=None,
            iops=None, state=None, encrypted=None
        )
        for key, value in kwargs.items():
            if key in self._volume_attributes:
                self._volume_attributes[key] = value

    def __getattr__(self, name):
        if name in self._volume_attributes:
            return self._volume_attributes[name]
        else:
            raise AttributeError

    def __eq__(self, other):
        """
        Compare set attributes on this stub to a boto3 ``Volume``.
        """
        equal = True
        for key, value in self._volume_attributes.items():
            other_value = getattr(other, key, None)
            if self._volume_attributes[key] is not None:
                if self._volume_attributes[key] != other_value:
                    equal = False
            if other_value is not None:
                if self._volume_attributes[key] != other_value:
                    equal = False
        return equal

    def __ne__(self, other):
        """
        Negative comparison. See ``VolumeStub.__eq__``.
        """
        return not self.__eq__(other)


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
        :rtype: ``VolumeStub``
        """
        volume = VolumeStub()

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
        volume.state = start_state

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
        :rtype: `dict`
        """
        if attach_type == self.A.MISSING_ATTACH_DATA:
            return None
        elif attach_type == self.A.MISSING_INSTANCE_ID:
            attach_data = dict()
            attach_data['Device'] = u'/dev/sdf'
            attach_data['InstanceId'] = ''
            return attach_data
        elif attach_type == self.A.MISSING_DEVICE:
            attach_data = dict()
            attach_data['Device'] = ''
            attach_data['InstanceId'] = u'i-xyz'
            return attach_data
        elif attach_type == self.A.ATTACH_SUCCESS:
            attach_data = dict()
            attach_data['Device'] = u'/dev/sdf'
            attach_data['InstanceId'] = u'i-xyz'
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
            volume.state = self._pick_end_state(operation, state_type)
            volume.attachments = [self._pick_attach_data(attach_data)]
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
        self.assertEqual(volume.state, u'available')

    def test_destroy_success(self):
        """
        Assert that successful volume destruction leads to valid end state.
        """
        volume = self._process_volume(self.V.DESTROY, self.S.DESTINATION_STATE)
        self.assertEquals(volume.state, u'')

    def test_attach_sucess(self):
        """
        Test if successful attach volume operation leads to expected state.
        """
        volume = self._process_volume(self.V.ATTACH, self.S.DESTINATION_STATE)
        self.assertEqual([volume.state, volume.attachments[0]['Device'],
                          volume.attachments[0]['InstanceId']],
                         [u'in-use', u'/dev/sdf', u'i-xyz'])

    def test_detach_success(self):
        """
        Test if successful detach volume operation leads to expected state.
        """
        volume = self._process_volume(self.V.DETACH, self.S.DESTINATION_STATE,
                                      self.A.DETACH_SUCCESS)
        self.assertEqual(volume.state, u'available')


class EBSCloudInterfaceTests(
        make_icloudapi_tests(
            blockdevice_api_factory=(
                lambda test_case: ebsblockdeviceapi_for_test(
                    test_case=test_case)))):

    """
    ``ICloudAPI`` adherence tests for ``EBSBlockDeviceAPI``.
    """
