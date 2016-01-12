# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Functional tests for ``flocker.node.agents.gce`` using a GCE cluster.

In order to run these tests you'll need to define the following environment
variables::

    FLOCKER_FUNCTIONAL_TEST=TRUE
    FLOCKER_FUNCTIONAL_TEST_CLOUD_CONFIG_FILE=$HOME/acceptance.yml
    FLOCKER_FUNCTIONAL_TEST_CLOUD_PROVIDER=gce

The configuration stanza for the GCE backend should resemble:
``
gce:
    zone: <gce-region>
    project: <gce-project-name>
``

Note that, at this time, authentication is done using the implicit VM service
account.  When creating your GCE instance be sure to check ``Allow API access
to all Google Cloud services in the same project.``

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


def gceblockdeviceapi_for_test(test_case):
    """
    Create a ``GCEBlockDeviceAPI`` for use by tests.
    """
    return get_blockdeviceapi_with_cleanup(test_case, ProviderType.gce)


class GCEBlockDeviceAPIInterfaceTests(
        make_iblockdeviceapi_tests(
            blockdevice_api_factory=gceblockdeviceapi_for_test,
            minimum_allocatable_size=get_minimum_allocatable_size(),
            device_allocation_unit=get_device_allocation_unit(),
            unknown_blockdevice_id_factory=lambda test: u"a1234678",
        )
):
    """
    :class:`IBlockDeviceAPI` Interface adherence Tests for
    :class:`GCEBlockDeviceAPI`.
    """

    def test_attach_elsewhere_attached_volume(self):
        # This test in make_iblockdevice_api is a terrible hack:
        # https://clusterhq.atlassian.net/browse/FLOC-1839
        # Rather than add racy code that checks for if a volume is attached
        # before attempting the attach, just skip this test for this driver.
        # TODO(mewert): replace with a good test.
        pass


class GCEBlockDeviceAPITests(TestCase):
    """
    Tests for :class:`GCEBlockDeviceAPI`.
    """

    def test_multiple_cluster(self):
        """
        Two :class:`GCEBlockDeviceAPI` instances can be run with different
        cluster_ids. Volumes in one cluster do not show up in listing from the
        other.
        """
        gce_block_device_api_1 = gceblockdeviceapi_for_test(self)
        gce_block_device_api_2 = gceblockdeviceapi_for_test(self)

        cluster_1_dataset_id = uuid4()
        cluster_2_dataset_id = uuid4()

        gce_block_device_api_1.create_volume(cluster_1_dataset_id,
                                             get_minimum_allocatable_size())

        gce_block_device_api_2.create_volume(cluster_2_dataset_id,
                                             get_minimum_allocatable_size())

        self.assertEqual([cluster_1_dataset_id],
                         list(x.dataset_id
                              for x in gce_block_device_api_1.list_volumes()))
        self.assertEqual([cluster_2_dataset_id],
                         list(x.dataset_id
                              for x in gce_block_device_api_2.list_volumes()))
