# -*- test-case-name: flocker.node.agents.functional.test_cinder,flocker.node.agents.functional.test_cinder_behaviour -*- # noqa
# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
A Cinder implementation of the ``IBlockDeviceAPI``.
"""
import time
from uuid import UUID

from bitmath import Byte, GiB

from eliot import Message

from pyrsistent import PRecord, field

from keystoneclient.openstack.common.apiclient.exceptions import (
    NotFound as CinderNotFound,
    HttpError as KeystoneHttpError,
)
from keystoneclient.auth import get_plugin_class
from keystoneclient.session import Session
from keystoneclient_rackspace.v2_0 import RackspaceAuth
from cinderclient.client import Client as CinderClient
from novaclient.client import Client as NovaClient
from novaclient.exceptions import NotFound as NovaNotFound
from novaclient.exceptions import ClientException as NovaClientException

from twisted.python.filepath import FilePath

from zope.interface import implementer, Interface

from ...common import (
    interface_decorator, get_all_ips, ipaddress_from_string
)
from .blockdevice import (
    IBlockDeviceAPI, BlockDeviceVolume, UnknownVolume, AlreadyAttachedVolume,
    UnattachedVolume, get_blockdevice_volume,
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
    def create(size, metadata=None):
        """
        Creates a volume.

        :param size: Size of volume in GiB
        :param metadata: Optional metadata to set on volume creation
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


def wait_for_volume(volume_manager, expected_volume,
                    expected_status=u'available',
                    time_limit=60):
    """
    Wait for a ``Volume`` with the same ``id`` as ``expected_volume`` to be
    listed and to have a ``status`` value of ``expected_status``.

    :param ICinderVolumeManager volume_manager: An API for listing volumes.
    :param Volume expected_volume: The ``Volume`` to wait for.
    :param unicode expected_status: The ``Volume.status`` to wait for.
    :param int time_limit: The maximum time, in seconds, to wait for the
        ``expected_volume`` to have ``expected_status``.
    :raises Exception: If ``expected_volume`` with ``expected_status`` is not
        listed within ``time_limit``.
    :returns: The listed ``Volume`` that matches ``expected_volume``.
    """
    start_time = time.time()
    # Log stuff happening in this loop.  FLOC-1833.
    while True:
        # Could be more efficient.  FLOC-1831
        for listed_volume in volume_manager.list():
            if listed_volume.id == expected_volume.id:
                # Could miss the expected status because race conditions.
                # FLOC-1832
                if listed_volume.status == expected_status:
                    return listed_volume

        elapsed_time = time.time() - start_time
        if elapsed_time < time_limit:
            time.sleep(1.0)
        else:
            raise Exception(
                'Timed out while waiting for volume. '
                'Expected Volume: {!r}, '
                'Expected Status: {!r}, '
                'Elapsed Time: {!r}, '
                'Time Limit: {!r}.'.format(
                    expected_volume, expected_status, elapsed_time, time_limit
                )
            )


def _extract_nova_server_addresses(addresses):
    """
    :param dict addresses: A ``dict`` mapping OpenStack network names
        to lists of address dictionaries in that network assigned to a
        server.
    :return: A ``set`` of all the IPv4 and IPv6 addresses from the
        ``addresses`` attribute of a ``Server``.
    """
    all_addresses = set()
    for network_name, addresses in addresses.items():
        for address_info in addresses:
            all_addresses.add(
                ipaddress_from_string(address_info['addr'])
            )

    return all_addresses


@implementer(IBlockDeviceAPI)
class CinderBlockDeviceAPI(object):
    """
    A cinder implementation of ``IBlockDeviceAPI`` which creates block devices
    in an OpenStack cluster using Cinder APIs.
    """
    def __init__(self,
                 cinder_volume_manager,
                 nova_volume_manager, nova_server_manager,
                 cluster_id):
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
        Find the ``ACTIVE`` Nova API server with a subset of the IPv4 and IPv6
        addresses on this node.
        """
        local_ips = get_all_ips()
        api_ip_map = {}
        matching_instances = []
        for server in self.nova_server_manager.list():
            # Servers which are not active will not have any IP addresses
            if server.status != u'ACTIVE':
                continue
            api_addresses = _extract_nova_server_addresses(server.addresses)
            # Only do subset comparison if there were *some* IP addresses;
            # non-ACTIVE servers will have an empty list of IP addresses and
            # lead to incorrect matches.
            if api_addresses and api_addresses.issubset(local_ips):
                matching_instances.append(server.id)
            else:
                for ip in api_addresses:
                    api_ip_map[ip] = server.id

        # If we've got this correct there should only be one matching instance.
        # But we don't currently test this directly. See FLOC-2281.
        if len(matching_instances) == 1:
            return matching_instances[0]
        # If there was no match, or if multiple matches were found, log an
        # error containing all the local and remote IPs.
        COMPUTE_INSTANCE_ID_NOT_FOUND(
            local_ips=local_ips, api_ips=api_ip_map
        ).write()

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
        )
        Message.new(message_type=CINDER_CREATE,
                    blockdevice_id=requested_volume.id).write()
        created_volume = wait_for_volume(
            volume_manager=self.cinder_volume_manager,
            expected_volume=requested_volume,
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
        for cinder_volume in self.cinder_volume_manager.list():
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
        attached_volume = wait_for_volume(
            volume_manager=self.cinder_volume_manager,
            expected_volume=nova_volume,
            expected_status=u'in-use',
        )

        attached_volume = unattached_volume.set('attached_to', attach_to)

        return attached_volume

    def detach_volume(self, blockdevice_id):
        our_id = self.compute_instance_id()
        try:
            cinder_volume = self.cinder_volume_manager.get(blockdevice_id)
        except CinderNotFound:
            raise UnknownVolume(blockdevice_id)

        try:
            self.nova_volume_manager.delete_server_volume(
                server_id=our_id,
                attachment_id=blockdevice_id
            )
        except NovaNotFound:
            raise UnattachedVolume(blockdevice_id)

        # This'll blow up if the volume is deleted from elsewhere.  FLOC-1882.
        wait_for_volume(
            volume_manager=self.cinder_volume_manager,
            expected_volume=cinder_volume,
            expected_status=u'available',
        )

    def destroy_volume(self, blockdevice_id):
        try:
            self.cinder_volume_manager.delete(blockdevice_id)
        except CinderNotFound:
            raise UnknownVolume(blockdevice_id)

        while True:
            # Don't loop forever here.  FLOC-1853
            try:
                self.cinder_volume_manager.get(blockdevice_id)
            except CinderNotFound:
                break
            time.sleep(1.0)

    def get_device_path(self, blockdevice_id):
        try:
            cinder_volume = self.cinder_volume_manager.get(blockdevice_id)
        except CinderNotFound:
            raise UnknownVolume(blockdevice_id)

        # As far as we know you can not have more than one attachment,
        # but, perhaps we're wrong and there should be a test for the
        # multiple attachment case.  FLOC-1854.
        try:
            [attachment] = cinder_volume.attachments
        except ValueError:
            raise UnattachedVolume(blockdevice_id)

        # It could be attached somewher else...
        # https://clusterhq.atlassian.net/browse/FLOC-1830
        return FilePath(attachment['device'])


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
class _LoggingCinderVolumeManager(PRecord):
    _cinder_volumes = field(mandatory=True)


@auto_openstack_logging(INovaVolumeManager, "_nova_volumes")
class _LoggingNovaVolumeManager(PRecord):
    _nova_volumes = field(mandatory=True)


@auto_openstack_logging(INovaServerManager, "_nova_servers")
class _LoggingNovaServerManager(PRecord):
    _nova_servers = field(mandatory=True)


def cinder_api(cinder_client, nova_client, cluster_id):
    """
    :param cinderclient.v1.client.Client cinder_client: The Cinder API client
        whose ``volumes`` attribute will be supplied as the
        ``cinder_volume_manager`` parameter of ``CinderBlockDeviceAPI``.
    :param novaclient.v2.client.Client nova_client: The Nova API client whose
        ``volumes`` attribute will be supplied as the ``nova_volume_manager``
        parameter of ``CinderBlockDeviceAPI``.
    :param UUID cluster_id: A Flocker cluster ID.

    :returns: A ``CinderBlockDeviceAPI``.
    """
    logging_cinder = _LoggingCinderVolumeManager(
        _cinder_volumes=cinder_client.volumes
    )
    logging_nova_volume_manager = _LoggingNovaVolumeManager(
        _nova_volumes=nova_client.volumes
    )
    logging_nova_server_manager = _LoggingNovaServerManager(
        _nova_servers=nova_client.servers
    )
    return CinderBlockDeviceAPI(
        cinder_volume_manager=logging_cinder,
        nova_volume_manager=logging_nova_volume_manager,
        nova_server_manager=logging_nova_server_manager,
        cluster_id=cluster_id,
    )


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


def cinder_from_configuration(region, cluster_id, **config):
    """
    Build a ``CinderBlockDeviceAPI`` using configuration and credentials in
    ``config``.

    :param str region: The region "slug" for which to configure the object.
    :param cluster_id: The unique cluster identifier for which to configure the
        object.
    """
    session = Session(
        auth=_openstack_auth_from_config(**config),
        verify=_openstack_verify_from_config(**config)
        )
    cinder_client = CinderClient(
        session=session, region_name=region, version=1
    )
    nova_client = NovaClient(
        session=session, region_name=region, version=2
    )

    return cinder_api(
        cinder_client=cinder_client,
        nova_client=nova_client,
        cluster_id=cluster_id,
    )
