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
from fixtures import Fixture
from characteristic import attributes

from ..blockdevice import AlreadyAttachedVolume

from ..gce import get_machine_zone, get_machine_project
from ....provision._gce import GCEInstanceBuilder

from ..test.test_blockdevice import (
    make_iblockdeviceapi_tests
)

from ..test.blockdevicefactory import (
    ProviderType, get_blockdeviceapi_with_cleanup,
    get_minimum_allocatable_size, get_device_allocation_unit
)

from ....testtools import TestCase


@attributes(['compute', 'project', 'zone'])
class GCEComputeTestObjects(Fixture):
    """
    Fixture for creating GCE resources that will be cleaned up at the end of
    the test.

    :ivar compute: The GCE compute interface object.
    :ivar project: The GCE project to create resources within.
    :ivar zone: The GCE zone to create resources within.
    """

    def _get_instance_builder(self):
        """
        Returns an instance builder that can be used to create GCE instances.
        """
        return GCEInstanceBuilder(
            compute=self.compute,
            project=self.project,
            zone=self.zone
        )

    def create_instance(self, instance_name):
        """
        Creates a GCE instance that will be destroyed at the end of the test.
        Blocks until the creation has concluded.

        :param unicode instance_name: The name of the new instance.

        :returns GCEInstance: The instance to use in the tests.
        """
        instance = self._get_instance_builder().create_instance(
            instance_name,
            machine_type=u"f1-micro"
        )
        self.addCleanup(lambda: instance.destroy())
        return instance


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
        #
        # See ``GCEBlockDeviceAPITests.test_attach_elsewhere_attached_volume``
        # for a GCE specific implementation of this test that is not based on
        # the hack.
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

    def test_attach_elsewhere_attached_volume(self):
        """
        An attempt to attach a ``BlockDeviceVolume`` already attached to
        another host raises ``AlreadyAttachedVolume``.
        """
        api = gceblockdeviceapi_for_test(self)
        gce_fixture = self.useFixture(GCEComputeTestObjects(
            compute=api._compute,
            project=get_machine_project(),
            zone=get_machine_zone()
        ))

        instance_name = u"functional-test-" + unicode(uuid4())
        other_instance = gce_fixture.create_instance(instance_name)

        new_volume = api.create_volume(
            dataset_id=uuid4(),
            size=get_minimum_allocatable_size()
        )

        attached_volume = api.attach_volume(
            new_volume.blockdevice_id,
            attach_to=other_instance.name,
        )

        self.assertRaises(
            AlreadyAttachedVolume,
            api.attach_volume,
            blockdevice_id=attached_volume.blockdevice_id,
            attach_to=api.compute_instance_id(),
        )
