# -*- test-case-name: flocker.node.agents.functional.test_gce -*-
# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
A GCE Persistent Disk (PD) implementation of the ``IBlockDeviceAPI``.

The following resources are helpful to refer to while maintaining this
driver:
- Rest API: https://cloud.google.com/compute/docs/reference/latest/
- Python Client: https://cloud.google.com/compute/docs/tutorials/python-guide
- Python API: https://google-api-client-libraries.appspot.com/documentation/compute/v1/python/latest/ # noqa
- Python Oauth: https://developers.google.com/identity/protocols/OAuth2ServiceAccount#authorizingrequests # noqa
"""

import requests

from bitmath import GiB, Byte
from googleapiclient import discovery
from googleapiclient.errors import HttpError
from oauth2client.gce import AppAssertionCredentials
from pyrsistent import PClass, field
from socket import gethostname
from twisted.python.filepath import FilePath
from uuid import UUID
from zope.interface import implementer, Interface

from .blockdevice import (
    IBlockDeviceAPI, ICloudAPI, BlockDeviceVolume, AlreadyAttachedVolume,
    UnknownVolume, UnattachedVolume
)
from ...common import poll_until

# GCE instances have a metadata server that can be queried for information
# about the instance the code is being run on.
_METADATA_SERVER = u'http://169.254.169.254/computeMetadata/v1/'
_METADATA_HEADERS = {u'Metadata-Flavor': u'Google'}


class OperationPoller(Interface):
    """
    Interface for GCE operation resource polling. GCE operation resources
    should be polled from GCE until they reach a status of ``DONE``. The
    specific endpoint that should be polled for the operation is different for
    global operations vs zone operations. This interface provides an
    abstraction for that difference.
    """

    def poll(compute):
        """
        Get the latest version of the requested operation. This should block
        until the latest version of the requested operation is gotten.

        :param compute: The GCE compute python API object.

        :returns: A dict representing the latest version of the GCE operation
            resource.
        """


@implementer(OperationPoller)
class ZoneOperationPoller(PClass):
    """
    Implemenation of :class:`OperationPoller` for zone operations.

    :ivar unicode zone: The zone the operation occurred in.
    :ivar unicode project: The project the operation is under.
    :ivar unicode operation_name: The name of the operation.
    """
    zone = field(type=unicode)
    project = field(type=unicode)
    operation_name = field(type=unicode)

    def poll(self, compute):
        return compute.zoneOperations().get(
            project=self.project,
            zone=self.zone,
            operation=self.operation_name
        ).execute()


@implementer(OperationPoller)
class GlobalOperationPoller(PClass):
    """
    Implemenation of :class:`OperationPoller` for global operations.

    :ivar unicode project: The project the operation is under.
    :ivar unicode operation_name: The name of the operation.
    """
    project = field(type=unicode)
    operation_name = field(type=unicode)

    def poll(self, compute):
        return compute.globalOperations().get(
            project=self.project,
            operation=self.operation_name
        ).execute()


class MalformedOperation(Exception):
    """
    Error indicating that there was an error parsing a dictionary as a GCE
    operation resource.
    """


def _create_poller(operation):
    """
    Creates an operation poller from the passed in operation.

    :param operation: A dict representing a GCE operation resource.

    :returns: An :class:`OperationPoller` provider that can poll the status of
        the operation.
    """
    try:
        operation_name = operation['name']
    except KeyError:
        raise MalformedOperation(
            u"Failed to parse operation, could not find key "
            u"name in: {}".format(operation)
        )
    if 'zone' in operation:
        zone_url_parts = unicode(operation['zone']).split('/')
        try:
            project = zone_url_parts[-3]
            zone = zone_url_parts[-1]
        except IndexError:
            raise MalformedOperation(
                "'zone' key of operation had unexpected form: {}.\n"
                "Expected '(.*/)?<project>/zones/<zone>'.\n"
                "Full operation: {}.".format(operation['zone'], operation))
        return ZoneOperationPoller(
            zone=unicode(zone),
            project=unicode(project),
            operation_name=unicode(operation_name)
        )
    else:
        try:
            project = unicode(operation['selfLink']).split('/')[-4]
        except KeyError:
            raise MalformedOperation(
                u"Failed to parse global operation, could not find key "
                u"selfLink in: {}".format(operation)
            )
        except IndexError:
            raise MalformedOperation(
                "'selfLink' key of operation had unexpected form: {}.\n"
                "Expected '(.*/)?<project>/global/operations/<name>'.\n"
                "Full operation: {}.".format(operation['selfLink'], operation))
        return GlobalOperationPoller(
            project=unicode(project),
            operation_name=unicode(operation_name)
        )


def wait_for_operation(compute, operation, timeout_steps):
    """
    Blocks until a GCE operation is complete, or timeout passes.

    This function will then poll the operation until it reaches state
    'DONE' or times out, and then returns the final operation resource
    dict.

    :param compute: The GCE compute python API object.
    :param operation: A dict representing a pending GCE operation resource.
        This can be either a zone or a global operation.
    :param timeout_steps: Iterable of times in seconds to wait until timing out
        the operation.

    :returns dict: A dict representing the concluded GCE operation
        resource or `None` if the operation times out.
    """
    poller = _create_poller(operation)

    def finished_operation_result():
        latest_operation = poller.poll(compute)
        if latest_operation['status'] == 'DONE':
            return latest_operation
        return None

    return poll_until(finished_operation_result, timeout_steps)


def get_metadata_path(path):
    """
    Requests a metadata path from the metadata server available within GCE.

    The metadata server is a good way to query information about the currently
    running instance and project it is in. It is also the mechanism used to
    inject ssh public keys and service account session tokens into the VM.

    :param unicode path: The path on the metadata server to query.

    :returns unicode: The resulting value from the metadata server.
    """
    timeout_sec = 3
    r = requests.get(_METADATA_SERVER + path,
                     headers=_METADATA_HEADERS,
                     timeout=timeout_sec)
    return r.text


def get_machine_zone():
    """
    Returns the zone that the GCE instance running this code is running within.

    It does this by querying the metadata server.

    :returns unicode: The zone where the current instance is running.
    """
    # Transform "projects/<project-number>/zones/us-central1-f" to
    # "us-central1-f".
    return get_metadata_path('instance/zone').split('/')[-1]


def get_machine_project():
    """
    Returns the project that the GCE instance running this code is running
    within.

    It does this by querying the metadata server.

    :returns unicode: The project under which the current instance is running.
    """
    return get_metadata_path('project/project-id')


# The prefix added to dataset_ids to turn them into blockdevice_ids.
_PREFIX = 'flocker-v1-'


def _blockdevice_id_to_dataset_id(blockdevice_id):
    """
    Computes a dataset_id from a blockdevice_id.

    :param unicode blockdevice_id: The blockdevice_id to get the dataset_id
        for.

    :returns UUID: The corresponding dataset_id.
    """
    return UUID(blockdevice_id[len(_PREFIX):])


def _dataset_id_to_blockdevice_id(dataset_id):
    """
    Computes a blockdevice_id from a dataset_id.

    :param UUID dataset_id: The dataset_id to get the blockdevice_id for.

    :returns unicode: The corresponding blockdevice_id.
    """
    return _PREFIX + unicode(dataset_id)


def _extract_attached_to(disk):
    """
    Given a GCE disk resource, determines the unicode name of the machine that
    it is attached to.

    :param dict disk: A GCE disk resource as returned from the API.

    :returns: The `unicode` name of the instance the disk is attached to or
        `None` if it is not attached to anything.
    """
    # TODO(mewert): determine how this works with a disk being attached to
    # multiple machines, update comment above.
    users = disk.get('users', [])
    if not users:
        return None
    return unicode(users[0].split('/')[-1])


@implementer(IBlockDeviceAPI)
@implementer(ICloudAPI)
class GCEBlockDeviceAPI(object):
    """
    A GCE Persistent Disk (PD) implementation of ``IBlockDeviceAPI`` which
    creates block devices in a GCE project.

    Constraints imposed from GCE:
        - GCE does not have a grab-bag of metadata you can attach to disks.
            Instead, it has two fields in the disk resource you can set:
                - name (must be unique within a project,
                        limited to 63 characters,
                        must start with letter)
                - description (free form text field)
        - GCE does allow you to pick the blockdevice_id of your volumes (the
            unique identifier that will be used to identify your volume on
            subsequent API calls). In GCE terms this is the disk resource name.
        - GCE lets you filter on both of these string fields, but only for
            equals and not equals.
        - GCE lets you set a token in the SCSI info pages on your blockdevices
            every time you attach them to a VM so that symlinks are created at
            '/dev/disk/by-id/google-<token>'.
            - This technically is brittle to implementation, configuration, and
                version of udev and the SCSI driver within the guest OS.
        - GCE resource names and descriptions are immutable after creation.

    Design:
        - For a given dataset_id (06e07bcc-fea1-4810-8c6d-7487196998b6) prefix
            the dataset_id with "flocker-v1-" to get the unicode blockdevice-id
            (flocker-v1-06e07bcc-fea1-4810-8c6d-7487196998b6).
        - Set the name of the GCE disk resource to the blockdevice_id. This
            lets us perform operations on the disk only knowing its
            blockdevice_id.
        - Set the description of the disk resource to:
            "flocker-v1-cluster: <cluster-uuid>".
        - Whenever attaching a disk to an instance, set <token> to the
            blockdevice_id.

    Design implications:
        - The GCE disk names meet the length and format requirements, and are
            as unique as blockdevice_ids.
        - We can perform operations on a disk only knowing its blockdevice_id
            without making additional API calls or looking things up in a
            table.
        - dataset_id is a pure function of blockdevice_id and vice versa.
        - You can have multiple clusters within the same project.
        - Multiple clusters within the same project cannot have datasets with
            the same UUID.
        - We could add filtering by cluster by filtering on description.
        - The path of the device (or at least the path to a symlink to a path
            of the volume) is a pure function of blockdevice_id.
    """
    # TODO(mewert): Logging throughout.

    def __init__(self, cluster_id, project, zone):
        """
        Initialize the GCEBlockDeviceAPI.

        :param unicode project: The project where all GCE operations will take
            place.
        :param unicode zone: The zone where all GCE operations will take place.
        """
        # TODO(mewert): Also enable credentials via service account private
        # keys.
        credentials = AppAssertionCredentials(
            "https://www.googleapis.com/auth/cloud-platform")
        self._compute = discovery.build(
            'compute', 'v1', credentials=credentials)
        self._project = project
        self._zone = zone
        self._cluster_id = cluster_id
        # None signifies to use the default page size.
        self._page_size = None

    def _disk_resource_description(self):
        """
        Returns the value to be used in the description field of the disk
        resources for this cluster.

        :returns unicode: The value for the description.
        """
        return u"flocker-v1-cluster-id: " + unicode(self._cluster_id)

    def _do_blocking_operation(self, function, max_wait=35, **kwargs):
        """
        Perform a GCE operation, blocking until the operation completes.

        This will call `function` with the passed in keyword arguments plus
        additional keyword arguments for project and zone which come from the
        private member variables with the same name. It is expected that
        `function` returns an object that has an `execute()` method that
        returns a GCE operation resource dict.

        This function will then poll the operation until it reaches state
        'DONE' or times out, and then returns the final operation resource
        dict.

        :param function: Callable that takes keyword arguments project and
            zone, and returns an executable that results in a GCE operation
            resource dict as described above.
        :param int max_wait: The maximum amount of time to wait in seconds for
            the operation to complete.
        :param kwargs: Additional keyword arguments to pass to function.

        :returns dict: A dict representing the concluded GCE operation
            resource.
        """
        # TODO(mewert): Be more sophisticated about timeout and retry loop.
        # Look at EBS code, read up on how GCE behaves, potentially allow each
        # operation to specify its own timeout. Also pass a reactor in so you
        # can test the timeout error paths in unit tests. Also document what
        # happens on timeout.
        args = dict(project=self._project, zone=self._zone)
        args.update(kwargs)
        operation = function(**args).execute()
        # TODO(bcox) Perform a decent test of typical latencies for
        # operations within GCE and use that information to determine
        # an appropriate timeout. Until that is done, use the
        # following arbitrary timeout.
        return wait_for_operation(self._compute, operation, [1]*max_wait)

    def allocation_unit(self):
        """
        Can only allocate PDs in GiB units.

        Documentation claims `GB` but experimentally this was determined to
        actually be `GiB`.
        """
        return int(GiB(1).to_Byte().value)

    def list_volumes(self):
        # TODO(mewert) Walk the pages.
        result = self._compute.disks().list(project=self._project,
                                            zone=self._zone).execute()
        return list(
            BlockDeviceVolume(
                blockdevice_id=unicode(disk['name']),
                size=int(GiB(int(disk['sizeGb'])).to_Byte()),
                attached_to=_extract_attached_to(disk),
                dataset_id=_blockdevice_id_to_dataset_id(disk['name'])
            )
            for disk in result['items']
            if (disk['name'].startswith(_PREFIX) and
                disk['description'] == self._disk_resource_description())
        )

    def compute_instance_id(self):
        """
        GCE does operations based on the `name` of resources, and also
        assigns the name to the hostname
        """
        # TODO(mewert): Consider getting this from the metadata server instead.
        #               Technically people can change their hostname.
        return unicode(gethostname())

    def create_volume(self, dataset_id, size):
        blockdevice_id = _dataset_id_to_blockdevice_id(dataset_id)
        sizeGiB = int(Byte(size).to_GiB())
        config = dict(
            name=blockdevice_id,
            sizeGb=sizeGiB,
            description=self._disk_resource_description(),
        )
        # TODO(mewert): Verify timeout and error conditions.
        self._do_blocking_operation(
            self._compute.disks().insert, body=config)

        # TODO(mewert): Test creating a volume in cluster A in this project
        # with the same UUID as a volume in cluster B in the same project.
        # make that the logs and errors make this error obvious to the user
        return BlockDeviceVolume(
            blockdevice_id=blockdevice_id,
            size=int(GiB(sizeGiB).to_Byte()),
            attached_to=None,
            dataset_id=dataset_id,
        )

    def attach_volume(self, blockdevice_id, attach_to):
        config = dict(
            deviceName=blockdevice_id,
            autoDelete=False,
            boot=False,
            source=(
                "https://www.googleapis.com/compute/v1/projects/%s/zones/%s/"
                "disks/%s" % (self._project, self._zone, blockdevice_id)
            )
        )
        try:
            # TODO(mewert): Verify timeout and error conditions.
            # TODO(mewert): Test what happens when disk is attached RW to a
            #               different instance, raise the correct error.
            result = self._do_blocking_operation(
                self._compute.instances().attachDisk,
                instance=attach_to,
                body=config
            )
        except HttpError as e:
            if e.resp.status == 400:
                # TODO(mewert): verify with the rest API that this is the only
                # way to get a 400.
                raise UnknownVolume(blockdevice_id)
            else:
                raise e
        errors = result.get('error', {}).get('errors', [])
        for e in errors:
            if e.get('code') == u"RESOURCE_IN_USE_BY_ANOTHER_RESOURCE":
                raise AlreadyAttachedVolume(blockdevice_id)
        disk = self._compute.disks().get(project=self._project,
                                         zone=self._zone,
                                         disk=blockdevice_id).execute()
        return BlockDeviceVolume(
            blockdevice_id=blockdevice_id,
            size=int(GiB(int(disk['sizeGb'])).to_Byte()),
            attached_to=attach_to,
            dataset_id=_blockdevice_id_to_dataset_id(blockdevice_id),
        )

    def _get_attached_to(self, blockdevice_id):
        """
        Determines the instance a blockdevice is attached to.

        :param unicode blockdevice_id: The blockdevice_id of the blockdevice to
            query.

        :returns unicode: The name of the instance.

        :raises UnknownVolume: If there is no volume with the given id in the
            cluster.
        :raises UnattachedVolume: If the volume is not attached to any
            instance.
        """
        try:
            # TODO(mewert) verify timeouts and error conditions.
            disk = self._compute.disks().get(project=self._project,
                                             zone=self._zone,
                                             disk=blockdevice_id).execute()
        except HttpError as e:
            if e.resp.status == 404:
                # TODO(mewert) Verify with the rest API this is the only way to
                # get a 404.
                raise UnknownVolume(blockdevice_id)
            else:
                raise e
        attached_to = _extract_attached_to(disk)
        if not attached_to:
            raise UnattachedVolume(blockdevice_id)
        return attached_to

    def detach_volume(self, blockdevice_id):
        attached_to = self._get_attached_to(blockdevice_id)
        # TODO(mewert): Test this race (something else detaches right at this
        # point). Might involve putting all GCE interactions behind a zope
        # interface and then using a proxy implementation to inject code.
        self._do_blocking_operation(
            self._compute.instances().detachDisk, instance=attached_to,
            deviceName=blockdevice_id)
        return None

    def get_device_path(self, blockdevice_id):
        # TODO(mewert): Verify that we need this extra API call.
        self._get_attached_to(blockdevice_id)

        # TODO(mewert): Verify we can get away returning a symlink here, or
        # just walk the symlink.
        return FilePath(u"/dev/disk/by-id/google-" + blockdevice_id)

    def destroy_volume(self, blockdevice_id):
        try:
            # TODO(mewert) verify timeouts and error conditions.
            self._do_blocking_operation(
                self._compute.disks().delete,
                disk=blockdevice_id
            )
        except HttpError as e:
            if e.resp.status == 404:
                raise UnknownVolume(blockdevice_id)
            else:
                raise e
        return None

    def list_live_nodes(self):
        page_token = None
        done = False
        nodes = []
        while not done:
            result = self._compute.instances().list(
                project=self._project,
                zone=self._zone,
                maxResults=self._page_size,
                pageToken=page_token
            ).execute()
            page_token = result.get('nextPageToken')
            nodes.extend(result.get('items', []))
            done = not page_token
        return set(node.get("name") for node in nodes
                   if node.get("status") == "RUNNING")

    def start_node(self, node_id):
        self._do_blocking_operation(
            self._compute.instances().start,
            max_wait=5*60,
            instance=node_id
        )

    def stop_node(self, node_id):
        """
        Stops a node. This shuts the node down, but leaves the boot disk
        available so that it can be started again using ``start_node``.

        Note this is only used in the functional tests of start_node.

        :param unicode node_id: The compute_instance_id of the node to stop.
        """
        self._do_blocking_operation(
            self._compute.instances().stop,
            max_wait=5*60,
            instance=node_id
        )
