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

from keystoneclient.openstack.common.apiclient.exceptions import Unauthorized

from twisted.python.filepath import FilePath
from twisted.trial.unittest import SkipTest, SynchronousTestCase

from flocker.ca import RootCredential, AUTHORITY_CERTIFICATE_FILENAME

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

from ..cinder import wait_for_volume, _compute_instance_id


def cinderblockdeviceapi_for_test(test_case):
    """
    Create a ``CinderBlockDeviceAPI`` instance for use in tests.

    :param TestCase test_case: The test being run.

    :returns: A ``CinderBlockDeviceAPI`` instance.  Any volumes it creates will
        be cleaned up at the end of the test (using ``test_case``\ 's cleanup
        features).
    """
    return get_blockdeviceapi_with_cleanup(test_case, ProviderType.openstack)


# XXX Refactor this function to one instance
def openstack_clients():
    """
    Get a Nova client for use in tests.
    """
    try:
        cls, kwargs = get_blockdeviceapi_args(ProviderType.openstack)
    except InvalidConfig as e:
        raise SkipTest(str(e))
    return kwargs


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
            unknown_blockdevice_id_factory=lambda test: unicode(uuid4()),
        )
):
    """
    Interface adherence Tests for ``CinderBlockDeviceAPI``.
    """
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


class CinderHttpsTests(SynchronousTestCase):
    """
    Test connections to HTTPS-enabled OpenStack.
    """

    @staticmethod
    def _authenticates_ok(cinder_client):
        """
        Check connection is authorized.

        :return: True if client connected OK, False otherwise.
        """
        try:
            cinder_client.authenticate()
            return True
        except Unauthorized:
            return False

    def test_verify_false(self):
        """
        With the peer_verify field set to False, connection to the
        OpenStack servers always succeeds.
        """
        try:
            cls, kwargs = get_blockdeviceapi_args(
                ProviderType.openstack, peer_verify=False)
        except InvalidConfig as e:
            raise SkipTest(str(e))
        self.assertTrue(self._authenticates_ok(kwargs['cinder_client']))

    def test_verify_ca_path_no_match_fails(self):
        """
        With a CA file that does not match any CA, connection to the
        OpenStack servers fails.
        """
        path = FilePath(self.mktemp())
        path.makedirs()
        RootCredential.initialize(path, b"mycluster")
        try:
            cls, kwargs = get_blockdeviceapi_args(
                ProviderType.openstack, backend='openstack',
                auth_plugin='password', password='password', peer_verify=True,
                peer_ca_path=path.child(AUTHORITY_CERTIFICATE_FILENAME).path)
        except InvalidConfig as e:
            raise SkipTest(str(e))
        self.assertFalse(self._authenticates_ok(kwargs['cinder_client']))


class CinderDevicePathTests(SynchronousTestCase):
    """
    get_device_path returns the correct device.
    """
    def setUp(self):
        clients = openstack_clients()
        self.cinder = clients['cinder_client']
        self.nova = clients['nova_client']
        self.blockdevice_api = cinderblockdeviceapi_for_test(test_case=self)

    def test_get_device_path(self):
        """
        get_device_path returns the most recently attached device
        """
        this_instance_id = _compute_instance_id(
            servers=self.nova.servers.list()
        )

        cinder_volume = self.cinder.volumes.create(1)
        volume = wait_for_volume(
            volume_manager=self.cinder.volumes,
            expected_volume=cinder_volume,
        )

        devices_before = set(FilePath('/dev').children())

        attached_volume = self.nova.create_server_volume(
            server_id=instance_id,
            volume_id=volume.id,
            device=None,
        )
        volume = wait_for_volume(
            volume_manager=self.cinder.volumes,
            expected_volume=attached_volume,
            expected_status=u'in-use',
        )

        devices_after = set(FilePath('/dev').children())
        new_devices = devices_after - devices_before
        [new_device] = new_devices

        device_path = self.blockdevice_api.get_device_path(volume.id)

        self.assertEqual(device_path, new_device)

