# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Functional tests for ``flocker.node.agents.pd`` using a GCE cluster.
"""

from uuid import uuid4

from ..test.test_blockdevice import (
    make_iblockdeviceapi_tests
)

from ..test.blockdevicefactory import (
    ProviderType, get_blockdeviceapi_with_cleanup,
    get_minimum_allocatable_size, get_device_allocation_unit
)

from ....testtools import TestCase


def pdblockdeviceapi_for_test(test_case):
    """
    Create a ``PDBlockDeviceAPI`` for use by tests.
    """
    return get_blockdeviceapi_with_cleanup(test_case, ProviderType.gce)


class PDBlockDeviceAPIInterfaceTests(
        make_iblockdeviceapi_tests(
            blockdevice_api_factory=pdblockdeviceapi_for_test,
            minimum_allocatable_size=get_minimum_allocatable_size(),
            device_allocation_unit=get_device_allocation_unit(),
            unknown_blockdevice_id_factory=lambda test: u"a1234678",
        )
):
    """
    :class:`IBlockDeviceAPI` Interface adherence Tests for
    :class:`PDBlockDeviceAPI`.
    """

    def test_attach_elsewhere_attached_volume(self):
        # This test in make_iblockdevice_api is a terrible hack:
        # https://clusterhq.atlassian.net/browse/FLOC-1839
        # Rather than add racy code that checks for if a volume is attached
        # before attempting the attach, just skip this test for this driver.
        # TODO(mewert): replace with a good test.
        pass


class PDBlockDeviceAPITests(TestCase):
    """
    Tests for :class:`PDBlockDeviceAPI`.
    """

    def test_multiple_cluster(self):
        """
        Two :class:`PDBlockDeviceAPI` instances can be run with different
        cluster_ids. Volumes in one cluster do not show up in listing from the
        other.
        """
        pd_block_device_api_1 = pdblockdeviceapi_for_test(self)
        pd_block_device_api_2 = pdblockdeviceapi_for_test(self)

        cluster_1_dataset_id = uuid4()
        cluster_2_dataset_id = uuid4()

        pd_block_device_api_1.create_volume(cluster_1_dataset_id,
                                            get_minimum_allocatable_size())

        pd_block_device_api_2.create_volume(cluster_2_dataset_id,
                                            get_minimum_allocatable_size())

        self.assertEqual([cluster_1_dataset_id],
                         list(x.dataset_id
                              for x in pd_block_device_api_1.list_volumes()))
        self.assertEqual([cluster_2_dataset_id],
                         list(x.dataset_id
                              for x in pd_block_device_api_2.list_volumes()))
