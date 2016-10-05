# -*- test-case-name: flocker.node.agents.functional.test_cinder,flocker.node.agents.functional.test_cinder_behaviour -*- # noqa
# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
A Cinder implementation of the ``IBlockDeviceAPI``.
"""
from itertools import repeat
import json
import time
from uuid import UUID

from bitmath import Byte, GiB

from eliot import Message

from pyrsistent import PClass, field

from keystoneauth1.exceptions.catalog import EndpointNotFound
from keystoneclient.openstack.common.apiclient.exceptions import (
    HttpError as KeystoneHttpError,
)
from keystoneclient.auth import get_plugin_class
from keystoneclient.session import Session
from keystoneclient_rackspace.v2_0 import RackspaceAuth
from cinderclient.api_versions import get_api_version
from cinderclient.client import Client as CinderClient
from cinderclient.exceptions import NotFound as CinderClientNotFound
from novaclient.client import Client as NovaClient
from novaclient.exceptions import NotFound as NovaNotFound
from novaclient.exceptions import ClientException as NovaClientException

from twisted.python.filepath import FilePath
from twisted.python.components import proxyForInterface

from zope.interface import implementer, Interface

from ...common import (
    interface_decorator, get_all_ips, ipaddress_from_string,
    poll_until,
)
from .blockdevice import (
    IBlockDeviceAPI, BlockDeviceVolume, UnknownVolume, AlreadyAttachedVolume,
    UnattachedVolume, UnknownInstanceID, get_blockdevice_volume, ICloudAPI,
)
from .blockdevice_manager import (
    LabelledFilesystem, MountError, temporary_mount
)
from ._logging import (
    NOVA_CLIENT_EXCEPTION, KEYSTONE_HTTP_ERROR, COMPUTE_INSTANCE_ID_NOT_FOUND,
    OPENSTACK_ACTION, CINDER_CREATE
)

# The key name used for identifying the Flocker cluster_id in the metadata for
# a volume.
CLUSTER_ID_LABEL = u'flocker-cluster-id'

# The key name used for identifying the Flocker dataset_id in the metadata for
# a volume.
DATASET_ID_LABEL = u'flocker-dataset-id'

# The longest time we're willing to wait for a Cinder API call to complete.
CINDER_TIMEOUT = 600

# The longest time we're willing to wait for a Cinder volume to be destroyed
CINDER_VOLUME_DESTRUCTION_TIMEOUT = 300

CONFIG_DRIVE_LABEL = u"config-2"
METADATA_RELATIVE_PATH = ['openstack', 'latest', 'meta_data.json']


def metadata_from_config_drive(config_drive_label=CONFIG_DRIVE_LABEL):
    """
    Attempt to retrieve metadata from config drive.
    """
    try:
        mounted_fs = temporary_mount(
            LabelledFilesystem(label=config_drive_label),
            options=["ro"]
        )
    except MountError as e:
        Message.new(
            message_type=(
                u"flocker:node:agents:blockdevice:openstack:"
                u"compute_instance_id:configdrive_not_available"),
            error_message=unicode(e),
        ).write()
        return None

    with mounted_fs as mountpoint:
        metadata_file = mountpoint.descendant(METADATA_RELATIVE_PATH)
        try:
            content = metadata_file.getContent()
        except IOError as e:
            Message.new(
                message_type=(
                    u"flocker:node:agents:blockdevice:openstack:"
                    u"compute_instance_id:metadata_file_not_found"),
                error_message=unicode(e),
            ).write()
            return
        try:
            return json.loads(content)
        except ValueError as e:
            Message.new(
                message_type=(
                    u"flocker:node:agents:blockdevice:openstack:"
                    u"compute_instance_id:metadata_file_not_json"),
                error_message=unicode(e),
            ).write()
            return


def _openstack_logged_method(method_name, original_name):
    """
    Run a method and log additional information about any exceptions that are
    raised.

    :param str method_name: The name of the method of the wrapped object to
        call.
    :param str original_name: The name of the attribute of self where the
        wrapped object can be found.

    :return: A function which will call the method of the wrapped object and do
        the extra exception logging.
    """
    def _run_with_logging(self, *args, **kwargs):
        original = getattr(self, original_name)
        method = getattr(original, method_name)

        # See https://clusterhq.atlassian.net/browse/FLOC-2054
        # for ensuring all method arguments are serializable.
        with OPENSTACK_ACTION(operation=[method_name, args, kwargs]):
            try:
                return method(*args, **kwargs)
            except NovaClientException as e:
                NOVA_CLIENT_EXCEPTION(
                    code=e.code,
                    message=e.message,
                    details=e.details,
                    request_id=e.request_id,
                    url=e.url,
                    method=e.method,
                ).write()
                raise
            except KeystoneHttpError as e:
                KEYSTONE_HTTP_ERROR(
                    code=e.http_status,
                    message=e.message,
                    details=e.details,
                    request_id=e.request_id,
                    url=e.url,
                    method=e.method,
                    response=e.response.text,
                ).write()
                raise
    return _run_with_logging


def auto_openstack_logging(interface, original):
    """
    Create a class decorator which will add OpenStack-specific exception
    logging versions versions of all of the methods on ``interface``.
    Specifically, some Nova and Cinder client exceptions will have all of their
    details logged any time they are raised.

    :param zope.interface.InterfaceClass interface: The interface from which to
        take methods.
    :param str original: The name of an attribute on instances of the decorated
        class.  The attribute should refer to a provider of ``interface``.
        That object will have all of its methods called with additional
        exception logging to make more details of the underlying OpenStack API
        calls available.

    :return: The class decorator.
    """
    return interface_decorator(
        "auto_openstack_logging",
        interface,
        _openstack_logged_method,
        original,
    )


class ICinderVolumeManager(Interface):
    """
    The parts of ``cinderclient.v1.volumes.VolumeManager`` that we use.
    See:
    https://github.com/openstack/python-cinderclient/blob/master/cinderclient/v1/volumes.py#L135
    """

    # The OpenStack Cinder API documentation says the size is in GB (multiples
    # of 10 ** 9 bytes).  Real world observations indicate size is actually in
    # GiB (multiples of 2 ** 30).  So this method is documented as accepting
    # GiB values.  https://bugs.launchpad.net/openstack-api-site/+bug/1456631
    def create(size, metadata=None, display_name=None):
        """
        Creates a volume.

        :param size: Size of volume in GiB
        :param metadata: Optional metadata to set on volume creation
        :param display_name: Optional name of the volume
        :rtype: :class:`Volume`
        """

    def list():
        """
        Lists all volumes.

        :rtype: list of :class:`Volume`
        """

    def delete(volume_id):
        """
        Delete a volume.

        :param volume_id: The ID of the volume to delete.

        :raise CinderNotFound: If no volume with the specified ID exists.

        :return: ``None``
        """

    def get(volume_id):
        """
        Retrieve information about an existing volume.

        :param volume_id: The ID of the volume about which to retrieve
            information.

        :return: A ``Volume`` instance describing the identified volume.
        :rtype: :class:`Volume`
        """

    def set_metadata(volume, metadata):
        """
        Update/Set a volumes metadata.

        :param volume: The :class:`Volume`.
        :param metadata: A list of keys to be set.
        """


class INovaVolumeManager(Interface):
    """
    The parts of ``novaclient.v2.volumes.VolumeManager`` that we use.
    See:
    https://github.com/openstack/python-novaclient/blob/master/novaclient/v2/volumes.py
    """
    def create_server_volume(server_id, volume_id, device):
        """
        Attach a volume identified by the volume ID to the given server ID.

        :param server_id: The ID of the server
        :param volume_id: The ID of the volume to attach.
        :param device: The device name
        :rtype: :class:`Volume`
        """

    def delete_server_volume(server_id, attachment_id):
        """
        Detach the volume identified by the volume ID from the given server ID.

        :param server_id: The ID of the server
        :param attachment_id: The ID of the volume to detach.
        """

    def get(volume_id):
        """
        Retrieve information about an existing volume.

        :param volume_id: The ID of the volume about which to retrieve
            information.

        :return: A ``Volume`` instance describing the identified volume.
        :rtype: :class:`Volume`
        """


class INovaServerManager(Interface):
    """
    The parts of ``novaclient.v2.servers.ServerManager`` that we use.
    See:
    https://github.com/openstack/python-novaclient/blob/master/novaclient/v2/servers.py
    """
    def list():
        """
        Get a list of servers.
        """


class TimeoutException(Exception):
    """
    A timeout on waiting for volume to reach destination end state.
    :param expected_volume: the volume we were waiting on
    :param desired_state: the new state we wanted the volume to have
    :param elapsed_time: how much time we had been waiting for the volume
        to change the state
    """
    def __init__(self, expected_volume, desired_state, elapsed_time):
        self.expected_volume = expected_volume
        self.desired_state = desired_state
        self.elapsed_time = elapsed_time

    def __str__(self):
        return (
            'Timed out while waiting for volume. '
            'Expected Volume: {!r}, '
            'Expected State: {!r}, '
            'Elapsed Time: {!r}'.format(
                self.expected_volume, self.desired_state, self.elapsed_time)
            )


class UnexpectedStateException(Exception):
    """
    An unexpected state was encountered by a volume as a result of operation.
    """
    def __init__(self, expected_volume, desired_state, unexpected_state):
        self.expected_volume = expected_volume
        self.desired_state = desired_state
        self.unexpected_state = unexpected_state

    def __str__(self):
        return (
            'Unexpected state while waiting for volume. '
            'Expected Volume: {!r}, '
            'Expected State: {!r}, '
            'Reached State: {!r}'.format(
                self.expected_volume, self.desired_state,
                self.unexpected_state)
            )


class VolumeStateMonitor:
    """
    Monitor a volume until it reaches a nominated state.
    :ivar ICinderVolumeManager volume_manager: An API for listing volumes.
    :ivar Volume expected_volume: The ``Volume`` to wait for.
    :ivar unicode desired_state: The ``Volume.status`` to wait for.
    :ivar transient_states: A sequence of valid intermediate states.
        The states must be listed in the order that are expected to occur.
    :ivar int time_limit: The maximum time, in seconds, to wait for the
        ``expected_volume`` to have ``desired_state``.
    :raises: UnexpectedStateException: If ``expected_volume`` enters an
        invalid state.
    :raises TimeoutException: If ``expected_volume`` with
        ``desired_state`` is not listed within ``time_limit``.
    :returns: The listed ``Volume`` that matches ``expected_volume``.
    """
    def __init__(self, volume_manager, expected_volume,
                 desired_state, transient_states=(),
                 time_limit=CINDER_TIMEOUT):
        self.volume_manager = volume_manager
        self.expected_volume = expected_volume
        self.desired_state = desired_state
        self.transient_states = transient_states
        self.time_limit = time_limit
        self.start_time = time.time()

    def reached_desired_state(self):
        """
        Test whether the desired state has been reached.

        Raise an exception if a non-valid state is reached or if the
        desired state is not reached within the supplied time limit.
        """
        try:
            existing_volume = self.volume_manager.get(self.expected_volume.id)
        except CinderClientNotFound:
            elapsed_time = time.time() - self.start_time
            if elapsed_time > self.time_limit:
                raise TimeoutException(
                    self.expected_volume, self.desired_state, elapsed_time)
            return None
        # Could miss the expected status because race conditions.
        # FLOC-1832
        current_state = existing_volume.status
        if current_state == self.desired_state:
            return existing_volume
        elif current_state in self.transient_states:
            # Once an intermediate state is reached, the prior
            # states become invalid.
            idx = self.transient_states.index(current_state)
            if idx > 0:
                self.transient_states = self.transient_states[idx:]
        else:
            raise UnexpectedStateException(
                self.expected_volume, self.desired_state, current_state)


def wait_for_volume_state(volume_manager, expected_volume, desired_state,
                          transient_states=(), time_limit=CINDER_TIMEOUT):
    """
    Wait for a ``Volume`` with the same ``id`` as ``expected_volume`` to be
    listed and to have a ``status`` value of ``desired_state``.
    :param ICinderVolumeManager volume_manager: An API for listing volumes.
    :param Volume expected_volume: The ``Volume`` to wait for.
    :param unicode desired_state: The ``Volume.status`` to wait for.
    :param transient_states: A sequence of valid intermediate states.
    :param int time_limit: The maximum time, in seconds, to wait for the
        ``expected_volume`` to have ``desired_state``.
    :raises: UnexpectedStateException: If ``expected_volume`` enters an
        invalid state.
    :raises TimeoutException: If ``expected_volume`` with
        ``desired_state`` is not listed within ``time_limit``.
    :returns: The listed ``Volume`` that matches ``expected_volume``.
    """
    waiter = VolumeStateMonitor(
        volume_manager, expected_volume, desired_state, transient_states,
        time_limit)
    return poll_until(waiter.reached_desired_state, repeat(1))


def _extract_nova_server_addresses(addresses):
    """
    :param dict addresses: A ``dict`` mapping OpenStack network names
        to lists of address dictionaries in that network assigned to a
        server.
    :return: A ``set`` of all the IPv4 and IPv6 addresses from the
        ``addresses`` attribute of a ``Server``.
    """
    all_addresses = set()
    for _, addresses in addresses.items():
        for address_info in addresses:
            all_addresses.add(
                ipaddress_from_string(address_info['addr'])
            )

    return all_addresses


def _get_compute_id(local_ips, id_to_node_ips):
    """
    Compute the instance ID of the local machine.

    Expectation is that our local IPs intersect with one (only) of the
    remote nodes' sets of IPs.

    :param set local_ips: The local machine's IPs.
    :param id_to_node_ips: Mapping from instance IDs to sets of IPs, as
        reported by OpenStack.

    :return: Instance ID of local machine.
    """
    matching_instances = []
    for server_id, api_addresses in id_to_node_ips.items():
        if api_addresses.intersection(local_ips):
            matching_instances.append(server_id)

    # If we've got this correct there should only be one matching instance.
    # But we don't currently test this directly. See FLOC-2281.
    if len(matching_instances) == 1 and matching_instances[0]:
        return matching_instances[0]
    raise KeyError("Couldn't find matching node.")


def _nova_detach(nova_volume_manager, cinder_volume_manager,
                 server_id, cinder_volume):
    """
    Detach a Cinder volume from a Nova host and block until the volume has
    detached.

    :param nova_volume_manager: A ``nova.VolumManager``.
    :param cinder_volume_manager: A ``cinder.VolumManager``.
    :param server_id: The Nova server ID.
    :param cinder_volume: A cinder.Volume.
    """
    try:
        nova_volume_manager.delete_server_volume(
            server_id=server_id,
            attachment_id=cinder_volume.id
        )
    except NovaNotFound:
        raise UnattachedVolume(cinder_volume.id)

    # This'll blow up if the volume is deleted from elsewhere.  FLOC-1882.
    # Also note that we use the Cinder API here rather than the Nova API.
    # They may get out sync and it's the Cinder volume status that's important
    # if we are to successfully delete the volume next.
    wait_for_volume_state(
        volume_manager=cinder_volume_manager,
        expected_volume=cinder_volume,
        desired_state=u'available',
        transient_states=(u'in-use', u'detaching')
    )


@implementer(IBlockDeviceAPI)
@implementer(ICloudAPI)
class CinderBlockDeviceAPI(object):
    """
    A cinder implementation of ``IBlockDeviceAPI`` which creates block devices
    in an OpenStack cluster using Cinder APIs.
    """
    def __init__(self,
                 cinder_volume_manager,
                 nova_volume_manager, nova_server_manager,
                 cluster_id,
                 timeout=CINDER_VOLUME_DESTRUCTION_TIMEOUT,
                 time_module=None):
        """
        :param ICinderVolumeManager cinder_volume_manager: A client for
            interacting with Cinder API.
        :param INovaVolumeManager nova_volume_manager: A client for interacting
            with Nova volume API.
        :param INovaServerManager nova_server_manager: A client for interacting
            with Nova servers API.
        :param UUID cluster_id: An ID that will be included in the names of
            Cinder block devices in order to associate them with a particular
            Flocker cluster.
        """
        self.cinder_volume_manager = cinder_volume_manager
        self.nova_volume_manager = nova_volume_manager
        self.nova_server_manager = nova_server_manager
        self.cluster_id = cluster_id
        self._timeout = timeout
        if time_module is None:
            time_module = time
        self._time = time_module

    def allocation_unit(self):
        """
        1GiB is the minimum allocation unit described by the OpenStack
        Cinder API documentation.
         * http://developer.openstack.org/api-ref-blockstorage-v2.html#createVolume # noqa

        Some Cinder storage drivers may actually allocate more than
        this, but as long as the requested size is a multiple of this
        unit, the Cinder API will always report the size that was
        requested.
        """
        return int(GiB(1).to_Byte().value)

    def compute_instance_id(self):
        """
        Attempt to retrieve node UUID from the metadata in a config drive.
        Fall back to finging the ``ACTIVE`` Nova API server with an
        intersection of the IPv4 and IPv6 addresses on this node.
        """
        metadata = metadata_from_config_drive()
        if metadata:
            return metadata["uuid"]

        local_ips = get_all_ips()
        api_ip_map = {}
        id_to_node_ips = {}
        for server in self.nova_server_manager.list():
            # Servers which are not active will not have any IP addresses
            if server.status != u'ACTIVE':
                continue
            api_addresses = _extract_nova_server_addresses(server.addresses)
            id_to_node_ips[server.id] = api_addresses
            for ip in api_addresses:
                api_ip_map[ip] = server.id

        try:
            return _get_compute_id(local_ips, id_to_node_ips)
        except KeyError:
            # If there was no match, or if multiple matches were found, log an
            # error containing all the local and remote IPs.
            COMPUTE_INSTANCE_ID_NOT_FOUND(
                local_ips=local_ips, api_ips=api_ip_map
            ).write()
            raise UnknownInstanceID(self)

    def create_volume(self, dataset_id, size):
        """
        Create a block device using the ICinderVolumeManager.
        The cluster_id and dataset_id are stored as metadata on the volume.

        See:

        http://docs.rackspace.com/cbs/api/v1.0/cbs-devguide/content/POST_createVolume_v1__tenant_id__volumes_volumes.html
        """
        metadata = {
            CLUSTER_ID_LABEL: unicode(self.cluster_id),
            DATASET_ID_LABEL: unicode(dataset_id),
        }
        requested_volume = self.cinder_volume_manager.create(
            size=int(Byte(size).to_GiB().value),
            metadata=metadata,
            display_name="flocker-{}".format(dataset_id),
        )
        Message.new(message_type=CINDER_CREATE,
                    blockdevice_id=requested_volume.id).write()
        created_volume = wait_for_volume_state(
            volume_manager=self.cinder_volume_manager,
            expected_volume=requested_volume,
            desired_state=u'available',
            transient_states=(u'creating',),
        )
        return _blockdevicevolume_from_cinder_volume(
            cinder_volume=created_volume,
        )

    def list_volumes(self):
        """
        Return ``BlockDeviceVolume`` instances for all the Cinder Volumes that
        have the expected ``cluster_id`` in their metadata.

        See:

        http://docs.rackspace.com/cbs/api/v1.0/cbs-devguide/content/GET_getVolumesDetail_v1__tenant_id__volumes_detail_volumes.html
        """
        flocker_volumes = []
        for cinder_volume in self.cinder_volume_manager.list(detailed=True):
            if _is_cluster_volume(self.cluster_id, cinder_volume):
                flocker_volume = _blockdevicevolume_from_cinder_volume(
                    cinder_volume
                )
                flocker_volumes.append(flocker_volume)
        return flocker_volumes

    def attach_volume(self, blockdevice_id, attach_to):
        """
        Attach a volume to an instance using the Nova volume manager.
        """
        # The Cinder volume manager has an API for attaching volumes too.
        # However, it doesn't actually attach the volume: it only updates
        # internal state to indicate that the volume is attached!  Basically,
        # it is an implementation detail of how Nova attached volumes work and
        # no one outside of Nova has any business calling it.
        #
        # See
        # http://www.florentflament.com/blog/openstack-volume-in-use-although-vm-doesnt-exist.html
        unattached_volume = get_blockdevice_volume(self, blockdevice_id)
        if unattached_volume.attached_to is not None:
            raise AlreadyAttachedVolume(blockdevice_id)

        nova_volume = self.nova_volume_manager.create_server_volume(
            # Nova API expects an ID string not UUID.
            server_id=attach_to,
            volume_id=unattached_volume.blockdevice_id,
            # Have Nova assign a device file for us.
            device=None,
        )
        attached_volume = wait_for_volume_state(
            volume_manager=self.cinder_volume_manager,
            expected_volume=nova_volume,
            desired_state=u'in-use',
            transient_states=(u'available', u'attaching',),
        )

        attached_volume = unattached_volume.set('attached_to', attach_to)

        return attached_volume

    def detach_volume(self, blockdevice_id):
        try:
            cinder_volume = self.cinder_volume_manager.get(blockdevice_id)
        except CinderClientNotFound:
            raise UnknownVolume(blockdevice_id)
        server_id = _blockdevicevolume_from_cinder_volume(
            cinder_volume).attached_to

        _nova_detach(
            nova_volume_manager=self.nova_volume_manager,
            cinder_volume_manager=self.cinder_volume_manager,
            server_id=server_id,
            cinder_volume=cinder_volume,
        )

    def destroy_volume(self, blockdevice_id):
        """
        Detach Cinder volume identified by blockdevice_id.
        It will loop listing the volume until it is no longer there.
        if the volume is still there after the defined timeout,
        the function will just raise an exception and do nothing.

        :raises TimeoutException: If the volume is not deleted
            within the expected time. If that happens, it will be because after
            the timeout, the volume can still be listed. The volume will not
            be deleted unless further action is taken.
        """
        try:
            self.cinder_volume_manager.delete(blockdevice_id)
        except CinderClientNotFound:
            raise UnknownVolume(blockdevice_id)
        start_time = self._time.time()
        # Wait until the volume is not there or until the operation
        # timesout
        while(self._time.time() - start_time < self._timeout):
            try:
                self.cinder_volume_manager.get(blockdevice_id)
            except CinderClientNotFound:
                return
            self._time.sleep(1.0)
        # If the volume is not deleted, raise an exception
        raise TimeoutException(
            blockdevice_id,
            None,
            self._time.time() - start_time
        )

    def _get_device_path_virtio_blk(self, volume):
        """
        The virtio_blk driver allows a serial number to be assigned to virtual
        blockdevices.
        OpenStack will set a serial number containing the first 20
        characters of the Cinder block device ID.

        This was introduced in
        * https://github.com/openstack/nova/commit/3a47c02c58cefed0e230190b4bcef14527c82709  # noqa
        * https://bugs.launchpad.net/nova/+bug/1004328

        The udev daemon will read the serial number and create a
        symlink to the canonical virtio_blk device path.

        We do this because libvirt does not return the correct device path when
        additional disks have been attached using a client other than
        cinder. This is expected behaviour within Cinder and libvirt See
        https://bugs.launchpad.net/cinder/+bug/1387945 and
        http://libvirt.org/formatdomain.html#elementsDisks (target section)

        :param volume: The Cinder ``Volume`` which is attached.
        :returns: ``FilePath`` of the device created by the virtio_blk
            driver.
        """
        expected_path = FilePath(
            "/dev/disk/by-id/virtio-{}".format(volume.id[:20])
        )
        # Return the real path instead of the symlink to avoid two problems:
        #
        # 1. flocker-dataset-agent mounting volumes before udev has populated
        #    the by-id symlinks.
        # 2. Even if we mount with `/dev/disk/by-id/xxx`, the mounted
        #    filesystems are listed (in e.g. `/proc/mounts`) with the
        #    **target** (i.e. the real path) of the `/dev/disk/by-id/xxx`
        #    symlinks. This confuses flocker-dataset-agent (which assumes path
        #    equality is string equality), causing it to believe that
        #    `/dev/disk/by-id/xxx` has not been mounted, leading it to
        #    repeatedly attempt to mount the device.
        if expected_path.exists():
            return expected_path.realpath()
        else:
            raise UnattachedVolume(volume.id)

    def _get_device_path_api(self, volume):
        """
        Return the device path reported by the Cinder API.

        :param volume: The Cinder ``Volume`` which is attached.
        :returns: ``FilePath`` of the device created by the virtio_blk
            driver.
        """
        if volume.attachments:
            attachment = volume.attachments[0]
            if len(volume.attachments) > 1:
                # As far as we know you can not have more than one attachment,
                # but, perhaps we're wrong and there should be a test for the
                # multiple attachment case.  FLOC-1854.
                # Log a message if this ever happens.
                Message.new(
                    message_type=(
                        u'flocker:node:agents:blockdevice:openstack:'
                        u'get_device_path:'
                        u'unexpected_multiple_attachments'
                    ),
                    volume_id=unicode(volume.id),
                    attachment_devices=u','.join(
                        unicode(a['device']) for a in volume.attachments
                    ),
                ).write()
        else:
            raise UnattachedVolume(volume.id)

        return FilePath(attachment['device'])

    def get_device_path(self, blockdevice_id):
        """
        On Xen hypervisors (e.g. Rackspace) the Cinder API reports the correct
        device path. On Qemu / virtio_blk the actual device path may be
        different. So when we detect ``virtio_blk`` style device paths, we
        check the virtual disk serial number, which should match the first
        20 characters of the Cinder Volume UUID on platforms that we support.
        """
        try:
            cinder_volume = self.cinder_volume_manager.get(blockdevice_id)
        except CinderClientNotFound:
            raise UnknownVolume(blockdevice_id)

        device_path = self._get_device_path_api(cinder_volume)
        if _is_virtio_blk(device_path):
            device_path = self._get_device_path_virtio_blk(cinder_volume)

        return device_path

    # ICloudAPI:
    def list_live_nodes(self):
        return list(server.id for server in self.nova_server_manager.list()
                    if server.status == u'ACTIVE')

    def start_node(self, node_id):
        server = self.nova_server_manager.get(node_id)
        server.start()


def _is_virtio_blk(device_path):
    """
    Check whether the supplied device path is a virtio_blk device.

    We assume that virtio_blk device name always begin with `vd` whereas
    Xen devices begin with `xvd`.
    See https://www.kernel.org/doc/Documentation/devices.txt

    :param FilePath device_path: The device path returned by the Cinder API.
    :returns: ``True`` if it's a ``virtio_blk`` device, else ``False``.
    """
    return device_path.basename().startswith('vd')


def _is_cluster_volume(cluster_id, cinder_volume):
    """
    :param UUID cluster_id: The uuid4 of a Flocker cluster.
    :param Volume cinder_volume: The Volume with metadata to examine.
    :return: ``True`` if ``cinder_volume`` metadata has a
        ``CLUSTER_ID_LABEL`` value matching ``cluster_id`` else ``False``.
    """
    actual_cluster_id = cinder_volume.metadata.get(CLUSTER_ID_LABEL)
    if actual_cluster_id is not None:
        actual_cluster_id = UUID(actual_cluster_id)
        if actual_cluster_id == cluster_id:
            return True
    return False


def _blockdevicevolume_from_cinder_volume(cinder_volume):
    """
    :param Volume cinder_volume: The ``cinderclient.v1.volumes.Volume`` to
        convert.
    :returns: A ``BlockDeviceVolume`` based on values found in the supplied
        cinder Volume.
    """
    if cinder_volume.attachments:
        # There should only be one.  FLOC-1854.
        [attachment_info] = cinder_volume.attachments
        # Nova and Cinder APIs return ID strings. Convert to unicode.
        server_id = attachment_info['server_id'].decode("ascii")
    else:
        server_id = None

    return BlockDeviceVolume(
        blockdevice_id=unicode(cinder_volume.id),
        size=int(GiB(cinder_volume.size).to_Byte().value),
        attached_to=server_id,
        dataset_id=UUID(cinder_volume.metadata[DATASET_ID_LABEL])
    )


@auto_openstack_logging(ICinderVolumeManager, "_cinder_volumes")
class _LoggingCinderVolumeManager(object):

    def __init__(self, cinder_volumes):
        self._cinder_volumes = cinder_volumes


@auto_openstack_logging(INovaVolumeManager, "_nova_volumes")
class _LoggingNovaVolumeManager(PClass):
    _nova_volumes = field(mandatory=True)


@auto_openstack_logging(INovaServerManager, "_nova_servers")
class _LoggingNovaServerManager(PClass):
    _nova_servers = field(mandatory=True)


def _openstack_auth_from_config(auth_plugin='password', **config):
    """
    Create an OpenStack authentication plugin from the given configuration.

    :param str auth_plugin: The name of the authentication plugin to create.
    :param config: Parameters to supply to the authentication plugin.  The
        exact parameters depends on the authentication plugin selected.

    :return: The authentication object.
    """
    if auth_plugin == 'rackspace':
        plugin_class = RackspaceAuth
    else:
        plugin_class = get_plugin_class(auth_plugin)

    plugin_options = plugin_class.get_options()
    plugin_kwargs = {}
    for option in plugin_options:
        # option.dest is the python compatible attribute name in the plugin
        # implementation.
        # option.dest is option.name with hyphens replaced with underscores.
        if option.dest in config:
            plugin_kwargs[option.dest] = config[option.dest]

    return plugin_class(**plugin_kwargs)


def _openstack_verify_from_config(
        verify_peer=True, verify_ca_path=None, **config):
    """
    Create an OpenStack session from the given configuration.

    This turns a pair of options (a boolean indicating whether to
    verify, and a string for the path to the CA bundle) into a
    requests-style single value.

    If the ``verify_peer`` parameter is False, then no verification of
    the certificate will occur.  This setting is insecure!  Although the
    connections will be confidential, there is no authentication of the
    peer.  We're having a private conversation, but we don't know to
    whom we are speaking.

    If the ``verify_peer`` parameter is True (the default), then the
    certificate will be verified.

    If the ``verify_ca_path`` parameter is set, the certificate will be
    verified against the CA bundle at the path given by the
    ``verify_ca_path`` parameter.  This is useful for systems using
    self-signed certificates or private CA's.

    Otherwise, the certificate will be verified against the system CA's.
    This is useful for systems using well-known public CA's.

    :param bool verify_peer: Whether to check the peer's certificate.
    :param str verify_ca_path: Path to CA bundle.
    :param config: Other parameters in the config.

    :return: A verify option that can be passed to requests (and also to
        keystoneclient.session.Session)
    """
    if verify_peer:
        if verify_ca_path:
            verify = verify_ca_path
        else:
            verify = True
    else:
        verify = False

    return verify


def get_keystone_session(**config):
    """
    Create a Keystone session from a configuration stanza.

    :param dict config: Configuration necessary to authenticate a
        session for use with the CinderClient and NovaClient.

    :return: keystoneclient.Session
    """
    return Session(
        auth=_openstack_auth_from_config(**config),
        verify=_openstack_verify_from_config(**config)
        )


class Cinder1to2Adapter(proxyForInterface(ICinderVolumeManager, "_client_v2")):
    """
    Deal with an annoying difference in the method signature between
    cinderclient.client.{v1,v2}.volumes.VolumeManager
    """
    def create(self, size, metadata=None, display_name=None):
        """
        ``python-cinderclient.client.V1.VolumeManager.create`` uses
        display_name rather than name.
        """
        return self._client_v2.create(
            size=size,
            metadata=metadata,
            name=display_name
        )


def lazy_loading_proxy_for_interface(interface, loader):
    """
    Create a proxy for an interface which builds the wrapped object lazily.

    This is different than a normal ``proxyForInterface`` subclass in that the
    wrapped object is not supplied to the class initializer but instead
    generated lazily by the supplied ``loader`` function.

    :param Interface interface: The ``Interface`` describing the methods and
        attributes that will be available on te returned proxy.
    :param loader: A no-argument function which will be called to create the
        wrapped object the first time one of the proxied objects is accessed.
    :returns: The proxy object.
    """
    class LazyLoadingProxy(proxyForInterface(interface, "_original")):
        _cached_original = None

        def __init__(self):
            """
            The initializer of a class generated by ``proxyForInterface``
            expects the wrapped "original" object as an argument.  Overrride
            that here.
            """

        @property
        def _original(self):
            if self._cached_original is None:
                self._cached_original = loader()
            return self._cached_original
    return LazyLoadingProxy()


CINDER_API_METADATA_IN_PRIORITY_ORDER = (
    dict(version=2, adapter_v1=Cinder1to2Adapter),
    dict(version=1, adapter_v1=lambda client: client),
)

CINDER_V1_ADAPTERS = {
    v["version"]: v["adapter_v1"]
    for v in CINDER_API_METADATA_IN_PRIORITY_ORDER
}

CINDER_API_SUPPORTED_VERSIONS = tuple(
    v["version"] for v in CINDER_API_METADATA_IN_PRIORITY_ORDER
)


class CinderAPIVersionDetectionFailure(EnvironmentError):
    """
    Unable to connect to a supported version of the Cinder API.
    """
    _template = "CinderAPIVersionDetectionFailure(endpoint_errors={!r})"

    def __init__(self, endpoint_errors):
        self.endpoint_errors = endpoint_errors

    def __str__(self):
        return self._template.format(
            self.endpoint_errors,
        )

    __repr__ = __str__


def get_cinder_client(session, region):
    """
    Create a Cinder (volume) client from a Keystone session.

    Try Cinder V2 and Cinder V1 in order and return the first client to
    successfully complete a ``list`` API call.

    :param keystoneclient.Session session: Authenticated Keystone session.
    :param str region: Openstack region.
    :return: A ``cinderclient.Client``
    """
    endpoint_errors = []
    for version in CINDER_API_SUPPORTED_VERSIONS:
        client = CinderClient(
            version=version, session=session, region_name=region
        )
        try:
            client.volumes.list(limit=1, detailed=False)
        except EndpointNotFound as e:
            endpoint_errors.append(e)
            continue
        else:
            return client
    raise CinderAPIVersionDetectionFailure(endpoint_errors)


def get_nova_v2_client(session, region):
    """
    Create a Nova (compute) client from a Keystone session.

    :param keystoneclient.Session session: Authenticated Keystone session.
    :param str region: Openstack region.
    :return: A novaclient.Client
    """
    return NovaClient(
        session=session, region_name=region, version=2
    )


def cinder_from_configuration(region, cluster_id, **config):
    """
    Build a ``CinderBlockDeviceAPI`` using configuration and credentials
    in ``config``.

    :param str region: The Openstack region to access.
    :param cluster_id: The unique identifier for the cluster to access.
    :param config: A dictionary of configuration options for Openstack.
    """
    def lazy_cinder_loader():
        """
        Build the v1 or v2 ``ICinderVolumeManager`` wrapped for compatibility
        with the v1 API and wrapped to provide logging of API calls.
        This will be invoked by ``LazyLoadingProxy`` the first time an
        ``ICinderVolumeManager`` attribute is accessed.
        The reason for the lazy loading of the volume manager is so that the
        the cinder API version detection can delayed until the
        ``flocker-dataset-agent`` loop has started. And the reason for that is
        so that exceptions (e.g. keystone connection errors) that occur during
        the cinder API version detection, do not occur when the
        ``CinderBlockDeviceAPI`` is initialized and crash the process. This way
        errors will be caught by the loop and the cinder API version detection
        will be retried until it succeeds.

        :returns: The ``ICinderVolumeManager`` wrapper.
        """
        session = get_keystone_session(**config)
        # Force authentication here for a clearer stack trace if the keystone
        # endpoint is not accessible.
        session.get_token()
        cinder_client = get_cinder_client(
            session=session,
            region=region,
        )

        wrapped_cinder_volume_manager = _LoggingCinderVolumeManager(
            cinder_client.volumes
        )
        cinder_client_version = get_api_version(cinder_client.version)
        # Add a Cinder v1 adapter if necessary
        adapted_cinder_volume_manager = CINDER_V1_ADAPTERS[
            cinder_client_version.ver_major
        ](wrapped_cinder_volume_manager)

        return adapted_cinder_volume_manager

    lazy_cinder_volume_manager_proxy = lazy_loading_proxy_for_interface(
        interface=ICinderVolumeManager,
        loader=lazy_cinder_loader,
    )

    nova_client = get_nova_v2_client(
        session=get_keystone_session(**config),
        region=region,
    )

    logging_nova_volume_manager = _LoggingNovaVolumeManager(
        _nova_volumes=nova_client.volumes
    )
    logging_nova_server_manager = _LoggingNovaServerManager(
        _nova_servers=nova_client.servers
    )
    return CinderBlockDeviceAPI(
        cinder_volume_manager=lazy_cinder_volume_manager_proxy,
        nova_volume_manager=logging_nova_volume_manager,
        nova_server_manager=logging_nova_server_manager,
        cluster_id=cluster_id,
    )
