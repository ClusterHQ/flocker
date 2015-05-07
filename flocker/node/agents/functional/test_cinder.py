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

from ....testtools import REALISTIC_BLOCKDEVICE_SIZE, skip_except
from ..cinder import cinder_api, wait_for_volume
# make_iblockdeviceapi_tests should really be in flocker.node.agents.testtools,
# but I want to keep the branch size down
from ..test.test_blockdevice import (
    make_iblockdeviceapi_tests, detach_destroy_volumes,
)
from ..test.blockdevicefactory import get_blockdeviceapi


def cinderblockdeviceapi_for_test(test_case, cluster_id):
    """
    Create a ``CinderBlockDeviceAPI`` instance for use in tests.

    :param TestCase test_case: The test being run.
    :param UUID cluster_id: The Flocker cluster ID for Cinder volumes.
    :returns: A ``CinderBlockDeviceAPI`` instance whose underlying
        ``cinderclient.v1.client.Client`` has a ``volumes`` attribute wrapped
        by ``TidyCinderVolumeManager`` to cleanup any lingering volumes that
        are created during the course of ``test_case``
    """
    return get_blockdeviceapi(test_case, "openstack")


# ``CinderBlockDeviceAPI`` only implements the ``create`` and ``list`` parts of
# ``IBlockDeviceAPI``. Skip the rest of the tests for now.
@skip_except(
    supported_tests=[
        'test_interface',
        'test_created_is_listed',
        'test_created_volume_attributes',
        'test_list_volume_empty',
        'test_listed_volume_attributes',
        'test_attach_unknown_volume',
        'test_attach_attached_volume',
        'test_attach_elsewhere_attached_volume',
        'test_attach_unattached_volume',
        'test_attached_volume_listed',
        'test_list_attached_and_unattached',
        'test_multiple_volumes_attached_to_host',
    ]
)
class CinderBlockDeviceAPIInterfaceTests(
        make_iblockdeviceapi_tests(
            blockdevice_api_factory=(
                lambda test_case: cinderblockdeviceapi_for_test(
                    test_case=test_case,
                    cluster_id=uuid4()
                )
            )
        )
):
    """
    Interface adherence Tests for ``CinderBlockDeviceAPI``.
    Block devices that are created in these tests will be cleaned up by
    ``TidyCinderVolumeManager``.
    """
    # def test_foreign_volume(self):
    #     """
    #     Non-Flocker Volumes are not listed.
    #     """
    #     cinder_client = tidy_cinder_client_for_test(test_case=self)
    #     requested_volume = cinder_client.volumes.create(
    #         size=Byte(REALISTIC_BLOCKDEVICE_SIZE).to_GB().value
    #     )
    #     wait_for_volume(
    #         volume_manager=cinder_client.volumes,
    #         expected_volume=requested_volume
    #     )

    #     self.addCleanup(cinder_client.connection.delete_volume,
    #                     requested_volume.id)
    #     self.assertEqual([], self.api.list_volumes())

    # def test_foreign_cluster_volume(self):
    #     """
    #     Test that list_volumes() excludes volumes belonging to
    #     other Flocker clusters.
    #     """
    #     blockdevice_api2 = cinderblockdeviceapi_for_test(
    #         test_case=self,
    #         cluster_id=uuid4(),
    #         )
    #     flocker_volume = blockdevice_api2.create_volume(
    #         dataset_id=uuid4(),
    #         size=REALISTIC_BLOCKDEVICE_SIZE,
    #         )

    #     self.addCleanup(blockdevice_api2.destroy_volume,
    #                     flocker_volume.blockdevice_id)
    #     self.assert_foreign_volume(flocker_volume)
