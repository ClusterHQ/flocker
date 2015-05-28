# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Functional tests for ``flocker.node.agents.cinder`` using a real OpenStack
cluster.

Ideally, there'd be some in-memory tests too. Some ideas:
 * Maybe start a `mimic` server and use it to at test just the authentication
   step.
 * Mimic doesn't currently fake the cinder APIs but perhaps we could contribute
   that feature.

See https://github.com/rackerlabs/mimic/issues/218
"""

from uuid import uuid4

from bitmath import Byte

from twisted.trial.unittest import SkipTest

# make_iblockdeviceapi_tests should really be in flocker.node.agents.testtools,
# but I want to keep the branch size down
from ..test.test_blockdevice import (
    make_iblockdeviceapi_tests,
)
from ..test.blockdevicefactory import (
    InvalidConfig, ProviderType, get_blockdeviceapi_args,
    get_blockdeviceapi_with_cleanup, get_device_allocation_unit,
    get_minimum_allocatable_size,
)

from ..cinder import wait_for_volume


def cinderblockdeviceapi_for_test(test_case):
    """
    Create a ``CinderBlockDeviceAPI`` instance for use in tests.

    :param TestCase test_case: The test being run.

    :returns: A ``CinderBlockDeviceAPI`` instance.  Any volumes it creates will
        be cleaned up at the end of the test (using ``test_case``\ 's cleanup
        features).
    """
    return get_blockdeviceapi_with_cleanup(test_case, ProviderType.openstack)


# ``CinderBlockDeviceAPI`` only implements the ``create`` and ``list`` parts of
# ``IBlockDeviceAPI``. Skip the rest of the tests for now.
class CinderBlockDeviceAPIInterfaceTests(
        make_iblockdeviceapi_tests(
            blockdevice_api_factory=(
                lambda test_case: cinderblockdeviceapi_for_test(
                    test_case=test_case,
                )
            ),
            minimum_allocatable_size=get_minimum_allocatable_size(),
            device_allocation_unit=get_device_allocation_unit(),
        )
):
    """
    Interface adherence Tests for ``CinderBlockDeviceAPI``.
    """

    # We haven't implemented resize functionality yet.
    def test_resize_destroyed_volume(self):
        raise SkipTest("Resize not implemented on Cinder - FLOC-1484")

    def test_resize_unknown_volume(self):
        raise SkipTest("Resize not implemented on Cinder - FLOC-1484")

    def test_resize_volume_listed(self):
        raise SkipTest("Resize not implemented on Cinder - FLOC-1484")

    def test_foreign_volume(self):
        """
        Non-Flocker Volumes are not listed.
        """
        try:
            cls, kwargs = get_blockdeviceapi_args(ProviderType.openstack)
        except InvalidConfig as e:
            raise SkipTest(str(e))
        cinder_client = kwargs["cinder_client"]
        requested_volume = cinder_client.volumes.create(
            size=int(Byte(self.minimum_allocatable_size).to_GiB().value)
        )
        self.addCleanup(
            cinder_client.volumes.delete,
            requested_volume.id,
        )
        wait_for_volume(
            volume_manager=cinder_client.volumes,
            expected_volume=requested_volume
        )
        self.assertEqual([], self.api.list_volumes())

    def test_foreign_cluster_volume(self):
        """
        Test that list_volumes() excludes volumes belonging to
        other Flocker clusters.
        """
        blockdevice_api2 = cinderblockdeviceapi_for_test(
            test_case=self,
            )
        flocker_volume = blockdevice_api2.create_volume(
            dataset_id=uuid4(),
            size=self.minimum_allocatable_size,
            )
        self.assert_foreign_volume(flocker_volume)
