# Copyright ClusterHQ Inc.  See LICENSE file for details.

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

from unittest import skipIf
from uuid import uuid4

from bitmath import Byte
import netifaces
import psutil

from keystoneclient.openstack.common.apiclient.exceptions import Unauthorized

from twisted.python.filepath import FilePath
from twisted.python.procutils import which
from twisted.trial.unittest import SkipTest, SynchronousTestCase

from flocker.ca import (
    RootCredential, AUTHORITY_CERTIFICATE_FILENAME, NodeCredential
)

# make_iblockdeviceapi_tests should really be in flocker.node.agents.testtools,
# but I want to keep the branch size down
from ..test.test_blockdevice import (
    make_iblockdeviceapi_tests, make_icloudapi_tests,
)
from ..test.blockdevicefactory import (
    InvalidConfig, ProviderType, get_blockdevice_config,
    get_blockdeviceapi_with_cleanup, get_device_allocation_unit,
    get_minimum_allocatable_size, get_openstack_region_for_test,
)
from ....testtools import REALISTIC_BLOCKDEVICE_SIZE, flaky, run_process

from ..cinder import (
    get_keystone_session, get_cinder_v1_client, get_nova_v2_client,
    wait_for_volume_state, UnexpectedStateException, UnattachedVolume,
    TimeoutException
)

from .logging import CINDER_VOLUME

# Tests requiring virtio can currently only be run on a devstack installation
# that is not within our CI system. This will be addressed with FLOC-2972.
#
# In the meantime, you can do the following (provided you have access):
#
# Connect to the devstack host:
#   ssh -A root@104.130.19.104
#
# From the devstack host, connect to the guest:
#   ssh -A ubuntu@10.0.0.3
#
# This is a shared machine that only ClusterHQ employees have access to. Make
# sure that no one else is using it at the same time.
#
# On the devstack guest do the following:
#   cd flocker
#   workon flocker
#
# Then update the branch to match the code you want to test.
#
# Then run these tests:
#
#   sudo /usr/bin/env \
#     FLOCKER_FUNCTIONAL_TEST_CLOUD_CONFIG_FILE=$PWD/acceptance.yml \
#     FLOCKER_FUNCTIONAL_TEST=TRUE \
#     FLOCKER_FUNCTIONAL_TEST_CLOUD_PROVIDER=devstack-openstack \
#     $(type -p trial) \
#     flocker.node.agents.functional.test_cinder.CinderAttachmentTests
require_virtio = skipIf(
    not which('virsh'), "Tests require the ``virsh`` command.")


def cinderblockdeviceapi_for_test(test_case):
    """
    Create a ``CinderBlockDeviceAPI`` instance for use in tests.

    :param TestCase test_case: The test being run.

    :returns: A ``CinderBlockDeviceAPI`` instance.  Any volumes it creates will
        be cleaned up at the end of the test (using ``test_case``\ 's cleanup
        features).
    """
    return get_blockdeviceapi_with_cleanup(test_case, ProviderType.openstack)


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
    def cinder_client(self):
        """
        :return: A ``cinderclient.Cinder`` instance.
        """
        try:
            config = get_blockdevice_config(ProviderType.openstack)
        except InvalidConfig as e:
            raise SkipTest(str(e))
        session = get_keystone_session(**config)
        region = get_openstack_region_for_test()
        return get_cinder_v1_client(session, region)

    def test_foreign_volume(self):
        """
        Non-Flocker Volumes are not listed.
        """
        cinder_client = self.cinder_client()
        requested_volume = cinder_client.volumes.create(
            size=int(Byte(self.minimum_allocatable_size).to_GiB().value)
        )
        CINDER_VOLUME(id=requested_volume.id).write()
        self.addCleanup(
            cinder_client.volumes.delete,
            requested_volume.id,
        )
        wait_for_volume_state(
            volume_manager=cinder_client.volumes,
            expected_volume=requested_volume,
            desired_state=u'available',
            transient_states=(u'creating',),
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
        CINDER_VOLUME(id=flocker_volume.blockdevice_id).write()
        self.assert_foreign_volume(flocker_volume)

    def test_name(self):
        """
        New volumes get a human-readable name.
        """
        cinder_client = self.cinder_client()
        dataset_id = uuid4()
        flocker_volume = self.api.create_volume(
            dataset_id=dataset_id,
            size=self.minimum_allocatable_size,
        )
        CINDER_VOLUME(id=flocker_volume.blockdevice_id).write()
        self.assertEqual(
            cinder_client.volumes.get(
                flocker_volume.blockdevice_id).display_name,
            u"flocker-{}".format(dataset_id))

    @flaky(u'FLOC-3347')
    def test_get_device_path_device(self):
        return super(
            CinderBlockDeviceAPIInterfaceTests,
            self).test_get_device_path_device()


class CinderCloudAPIInterfaceTests(
        make_icloudapi_tests(
            blockdevice_api_factory=(
                lambda test_case: cinderblockdeviceapi_for_test(
                    test_case=test_case,
                )
            ),
        )
):
    """
    ``ICloudAPI`` adherence tests for ``CinderBlockDeviceAPI``.
    """


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
            config = get_blockdevice_config(ProviderType.openstack)
        except InvalidConfig as e:
            raise SkipTest(str(e))
        config['peer_verify'] = False
        session = get_keystone_session(**config)
        region = get_openstack_region_for_test()
        cinder_client = get_cinder_v1_client(session, region)
        self.assertTrue(self._authenticates_ok(cinder_client))

    def test_verify_ca_path_no_match_fails(self):
        """
        With a CA file that does not match any CA, connection to the
        OpenStack servers fails.
        """
        path = FilePath(self.mktemp())
        path.makedirs()
        RootCredential.initialize(path, b"mycluster")
        try:
            config = get_blockdevice_config(ProviderType.openstack)
        except InvalidConfig as e:
            raise SkipTest(str(e))
        config['backend'] = 'openstack'
        config['auth_plugin'] = 'password'
        config['password'] = 'password'
        config['peer_verify'] = True
        config['peer_ca_path'] = path.child(
            AUTHORITY_CERTIFICATE_FILENAME).path
        session = get_keystone_session(**config)
        region = get_openstack_region_for_test()
        cinder_client = get_cinder_v1_client(session, region)
        self.assertFalse(self._authenticates_ok(cinder_client))


class VirtIOClient:
    """
    Provide access to libvirt on the host machine from guest machines

    This class allows the guest to attach and detach disks from the
    host.
    """
    def __init__(self, instance_id, url):
        self.instance_id = instance_id
        self.url = url

    @classmethod
    def using_insecure_tls(cls, instance_id, tempdir):
        """
        Create an insecure connection to the VM host.

        The credentials for this connection only allow unverified
        connections to the TLS endpoint of libvirtd.  The libvirtd
        server must be configured to not verify the client credentials,
        with server configuration ``tls_no_verify_certificate=1`` and
        ``tls_no_verify_address=1``.

        This would be vulnerable to MITM attacks, but is used for
        communication to the routing gateway (in particular from VM
        guest to VM host), where a MITM attack is unlikely.

        The tests require that disks are attached using libvirt, but not
        using Cinder, as the problem they test is libvirt disks that are
        not known by Cinder.  Note, this rules out solutions using
        ``mknod`` directly on the guest.

        Creating a TLS connection is one of the simplest ways to set-up
        libvirtd to listen on a network socket.  Disabling the actual
        certificate verification on both ends of the connection allows
        connection of the TLS endpoint without sharing any files (e.g.
        CA cert and key, or a CSR).  This means the tests are contained
        on one guest, with only a network connection required to attach
        and delete nodes from the host.

        :param instance_id: The UUID of the guest instance.
        :param FilePath tempdir: A temporary directory that will exist
            until the VirtIOClient is done.
        """
        url = "qemu://{}/system?no_verify=1&pkipath={}".format(
            cls._get_default_gateway(), tempdir.path
        )
        cls.create_credentials(tempdir)
        return cls(instance_id, url)

    @staticmethod
    def create_credentials(path):
        """
        Create PKI credentials for TLS access to libvirtd.

        Credentials are not signed by the host CA. This only allows
        unverified access but removes the need to transfer files
        between the host and the guest.
        """
        # Create CA and client key pairs
        ca = RootCredential.initialize(path, b"CA")
        ca_file = path.child(AUTHORITY_CERTIFICATE_FILENAME)
        NodeCredential.initialize(path, ca, uuid='client')
        # Files must have specific names in the pkipath directory
        ca_file.moveTo(path.child('cacert.pem'))
        path.child('client.key').moveTo(path.child('clientkey.pem'))
        path.child('client.crt').moveTo(path.child('clientcert.pem'))

    @staticmethod
    def _get_default_gateway():
        gws = netifaces.gateways()
        return gws['default'][netifaces.AF_INET][0]

    def attach_disk(self, host_device, guest_device):
        """
        Attach a host disk to a device path on the guest.

        :param host_device: The device path on the host.
        :param guest_device: The basename of the device path on the
            guest.
        """
        run_process(["virsh", "-c", self.url, "attach-disk",
                    self.instance_id,
                    host_device, guest_device])

    def detach_disk(self, host_device):
        """
        Detach a host disk from the guest.

        :param host_device: The device path on the host.
        """
        run_process(["virsh", "-c", self.url, "detach-disk",
                    self.instance_id,
                    host_device])


class OpenStackFixture(object):
    def __init__(self, addCleanup):
        self.addCleanup = addCleanup
        self.setUp()

    def setUp(self):
        config = get_blockdevice_config(ProviderType.openstack)
        region = get_openstack_region_for_test()
        session = get_keystone_session(**config)
        self.cinder = get_cinder_v1_client(session, region)
        self.nova = get_nova_v2_client(session, region)
        self.blockdevice_api = cinderblockdeviceapi_for_test(test_case=self)

    def _detach(self, instance_id, volume):
        self.nova.volumes.delete_server_volume(instance_id, volume.id)
        return wait_for_volume_state(
            volume_manager=self.nova.volumes,
            expected_volume=volume,
            desired_state=u'available',
            transient_states=(u'in-use', u'detaching'),
        )

    def cleanup(self, instance_id, volume):
        volume.get()
        if volume.attachments:
            self._detach(instance_id, volume)
        self.cinder.volumes.delete(volume.id)


class CinderAttachmentTests(SynchronousTestCase):
    """
    Cinder volumes can be attached and return correct device path.
    """
    def setUp(self):
        super(CinderAttachmentTests, self).setUp()
        try:
            self.openstack = OpenStackFixture(self.addCleanup)
        except InvalidConfig as e:
            self.skipTest(str(e))
        self.cinder = self.openstack.cinder
        self.nova = self.openstack.nova
        self.blockdevice_api = self.openstack.blockdevice_api
        self._cleanup = self.openstack.cleanup

    def test_get_device_path_no_attached_disks(self):
        """
        get_device_path returns the most recently attached device
        """
        instance_id = self.blockdevice_api.compute_instance_id()

        cinder_volume = self.cinder.volumes.create(
            size=int(Byte(get_minimum_allocatable_size()).to_GiB().value)
        )
        CINDER_VOLUME(id=cinder_volume.id).write()
        self.addCleanup(self._cleanup, instance_id, cinder_volume)
        volume = wait_for_volume_state(
            volume_manager=self.cinder.volumes, expected_volume=cinder_volume,
            desired_state=u'available', transient_states=(u'creating',))

        devices_before = set(FilePath('/dev').children())

        attached_volume = self.nova.volumes.create_server_volume(
            server_id=instance_id,
            volume_id=volume.id,
            device=None,
        )
        volume = wait_for_volume_state(
            volume_manager=self.cinder.volumes,
            expected_volume=attached_volume,
            desired_state=u'in-use',
            transient_states=(u'available', u'attaching',),
        )

        devices_after = set(FilePath('/dev').children())
        new_devices = devices_after - devices_before
        [new_device] = new_devices

        device_path = self.blockdevice_api.get_device_path(volume.id)

        self.assertEqual(device_path.realpath(), new_device)


class VirtIOCinderAttachmentTests(SynchronousTestCase):
    @require_virtio
    def setUp(self):
        super(VirtIOCinderAttachmentTests, self).setUp()
        try:
            self.openstack = OpenStackFixture(self.addCleanup)
        except InvalidConfig as e:
            self.skipTest(str(e))
        self.cinder = self.openstack.cinder
        self.nova = self.openstack.nova
        self.blockdevice_api = self.openstack.blockdevice_api
        self._cleanup = self.openstack.cleanup

    def test_get_device_path_correct_with_attached_disk(self):
        """
        get_device_path returns the correct device name even when a non-Cinder
        volume has been attached. See FLOC-2859.
        """
        instance_id = self.blockdevice_api.compute_instance_id()

        host_device = "/dev/null"
        tmpdir = FilePath(self.mktemp())
        tmpdir.makedirs()
        virtio = VirtIOClient.using_insecure_tls(instance_id, tmpdir)
        virtio.attach_disk(host_device, "vdc")
        self.addCleanup(virtio.detach_disk, host_device)

        cinder_volume = self.cinder.volumes.create(
            size=int(Byte(get_minimum_allocatable_size()).to_GiB().value)
        )
        CINDER_VOLUME(id=cinder_volume.id).write()
        self.addCleanup(self._cleanup, instance_id, cinder_volume)
        volume = wait_for_volume_state(
            volume_manager=self.cinder.volumes, expected_volume=cinder_volume,
            desired_state=u'available', transient_states=(u'creating',))

        devices_before = set(FilePath('/dev').children())

        attached_volume = self.nova.volumes.create_server_volume(
            server_id=instance_id,
            volume_id=volume.id,
            device=None,
        )
        volume = wait_for_volume_state(
            volume_manager=self.cinder.volumes,
            expected_volume=attached_volume,
            desired_state=u'in-use',
            transient_states=(u'available', u'attaching',),
        )

        devices_after = set(FilePath('/dev').children())
        new_devices = devices_after - devices_before
        [new_device] = new_devices

        device_path = self.blockdevice_api.get_device_path(volume.id)

        self.assertEqual(device_path.realpath(), new_device)

    def test_disk_attachment_fails_with_conflicting_disk(self):
        """
        create_server_volume will raise an exception when Cinder attempts to
        attach a device to a path that is in use by a non-Cinder volume.
        """
        instance_id = self.blockdevice_api.compute_instance_id()

        host_device = "/dev/null"
        tmpdir = FilePath(self.mktemp())
        tmpdir.makedirs()
        virtio = VirtIOClient.using_insecure_tls(instance_id, tmpdir)
        virtio.attach_disk(host_device, "vdb")
        self.addCleanup(virtio.detach_disk, host_device)

        cinder_volume = self.cinder.volumes.create(
            size=int(Byte(get_minimum_allocatable_size()).to_GiB().value)
        )
        CINDER_VOLUME(id=cinder_volume.id).write()
        self.addCleanup(self._cleanup, instance_id, cinder_volume)
        volume = wait_for_volume_state(
            volume_manager=self.cinder.volumes, expected_volume=cinder_volume,
            desired_state=u'available', transient_states=(u'creating',))

        attached_volume = self.nova.volumes.create_server_volume(
            server_id=instance_id,
            volume_id=volume.id,
            device=None,
        )

        with self.assertRaises(UnexpectedStateException) as e:
            wait_for_volume_state(
                volume_manager=self.cinder.volumes,
                expected_volume=attached_volume,
                desired_state=u'in-use',
                transient_states=(u'available', u'attaching',),
            )
        self.assertEqual(e.exception.unexpected_state, u'available')

    def test_get_device_path_virtio_blk_error_without_udev(self):
        """
        ``get_device_path`` on systems using the virtio_blk driver raises
        ``UnattachedVolume`` if ``/dev/disks/by-id/xxx`` is not present.
        """
        instance_id = self.blockdevice_api.compute_instance_id()
        # Create volume
        cinder_volume = self.cinder.volumes.create(
            size=int(Byte(get_minimum_allocatable_size()).to_GiB().value)
        )
        CINDER_VOLUME(id=cinder_volume.id).write()
        self.addCleanup(self._cleanup, instance_id, cinder_volume)
        volume = wait_for_volume_state(
            volume_manager=self.cinder.volumes, expected_volume=cinder_volume,
            desired_state=u'available', transient_states=(u'creating',))

        # Suspend udevd before attaching the disk
        # List unpacking here ensures that the test will blow up if
        # multiple matching processes are ever found.
        [udev_process] = list(
            p for p in psutil.process_iter()
            if p.name().endswith('-udevd')
        )
        udev_process.suspend()
        self.addCleanup(udev_process.resume)

        # Attach volume
        attached_volume = self.nova.volumes.create_server_volume(
            server_id=instance_id,
            volume_id=volume.id,
            device=None,
        )
        volume = wait_for_volume_state(
            volume_manager=self.cinder.volumes,
            expected_volume=attached_volume,
            desired_state=u'in-use',
            transient_states=(u'available', u'attaching',),
        )

        self.assertRaises(
            UnattachedVolume,
            self.blockdevice_api.get_device_path,
            volume.id,
        )

    def test_get_device_path_virtio_blk_symlink(self):
        """
        ``get_device_path`` on systems using the virtio_blk driver
        returns the target of a symlink matching
        ``/dev/disks/by-id/virtio-<volume.id>``.
        """
        instance_id = self.blockdevice_api.compute_instance_id()
        # Create volume
        cinder_volume = self.cinder.volumes.create(
            size=int(Byte(get_minimum_allocatable_size()).to_GiB().value)
        )
        CINDER_VOLUME(id=cinder_volume.id).write()
        self.addCleanup(self._cleanup, instance_id, cinder_volume)
        volume = wait_for_volume_state(
            volume_manager=self.cinder.volumes,
            expected_volume=cinder_volume,
            desired_state=u'available',
            transient_states=(u'creating',))

        # Attach volume
        attached_volume = self.nova.volumes.create_server_volume(
            server_id=instance_id,
            volume_id=volume.id,
            device=None,
        )
        volume = wait_for_volume_state(
            volume_manager=self.cinder.volumes,
            expected_volume=attached_volume,
            desired_state=u'in-use',
            transient_states=(u'available', u'attaching',),
        )
        self.assertEqual(
            FilePath(
                '/dev/disk/by-id/virtio-{}'.format(volume.id[:20])
            ).realpath(),
            self.blockdevice_api.get_device_path(
                volume.id
            )
        )


class FakeTime(object):
    def __init__(self, initial_time):
        self._current_time = initial_time

    def time(self):
        return self._current_time

    def sleep(self, interval):
        self._current_time += interval


class BlockDeviceAPIDestroyTests(SynchronousTestCase):
    """
    Test for ``cinder.CinderBlockDeviceAPI.destroy_volume``
    """
    def setUp(self):
        self.api = cinderblockdeviceapi_for_test(test_case=self)

    def test_destroy_timesout(self):
        """
        If Cinder does not delete the volume within a specified amount of time,
        the destroy attempt fails by raising ``TimeoutException``.
        """
        new_volume = self.api.create_volume(
            dataset_id=uuid4(),
            size=int(REALISTIC_BLOCKDEVICE_SIZE.to_Byte()),
        )

        expected_timeout = 8
        # Using a fake no-op delete so it doesn't actually delete anything
        # (we don't need any actual volumes here, as we only need to verify
        # the timeout)
        self.patch(
            self.api.cinder_volume_manager,
            "delete",
            lambda *args, **kwargs: None
        )

        # Now try to delete it
        time_module = FakeTime(initial_time=0)
        self.patch(self.api, "_time", time_module)
        self.patch(self.api, "_timeout", expected_timeout)

        exception = self.assertRaises(
            TimeoutException,
            self.api.destroy_volume,
            blockdevice_id=new_volume.blockdevice_id,
        )

        self.assertEqual(
            expected_timeout,
            exception.elapsed_time
        )

        self.assertEqual(
            expected_timeout,
            time_module._current_time
        )
