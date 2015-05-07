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

# make_iblockdeviceapi_tests should really be in flocker.node.agents.testtools,
# but I want to keep the branch size down
from ..test.test_blockdevice import (
    make_iblockdeviceapi_tests,
)
from ..test.blockdevicefactory import (
    ProviderType, get_blockdeviceapi_args,
    get_blockdeviceapi_with_cleanup,
)
from ....testtools import REALISTIC_BLOCKDEVICE_SIZE

from ..cinder import wait_for_volume


def cinderblockdeviceapi_for_test(test_case):
    """
    Create a ``CinderBlockDeviceAPI`` instance for use in tests.

    :param TestCase test_case: The test being run.
    :returns: A ``CinderBlockDeviceAPI`` instance whose underlying
        ``cinderclient.v1.client.Client`` has a ``volumes`` attribute wrapped
        by ``TidyCinderVolumeManager`` to cleanup any lingering volumes that
        are created during the course of ``test_case``
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
            )
        )
):
    """
    Interface adherence Tests for ``CinderBlockDeviceAPI``.
    Block devices that are created in these tests will be cleaned up by
    ``TidyCinderVolumeManager``.
    """
    def test_foreign_volume(self):
        """
        Non-Flocker Volumes are not listed.
        """
        cls, kwargs = get_blockdeviceapi_args(ProviderType.openstack)
        cinder_volumes = kwargs["cinder_volume_manager"]
        requested_volume = cinder_volumes.create(
            size=Byte(REALISTIC_BLOCKDEVICE_SIZE).to_GB().value
        )
        self.addCleanup(
            cinder_volumes.delete,
            requested_volume.id,
        )
        wait_for_volume(
            volume_manager=cinder_volumes,
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
            size=REALISTIC_BLOCKDEVICE_SIZE,
            )
        self.assert_foreign_volume(flocker_volume)
