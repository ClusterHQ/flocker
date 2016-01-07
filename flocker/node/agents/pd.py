# -*- test-case-name: flocker.node.agents.functional.test_pd -*-
# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
A PD implementation of the ``IBlockDeviceAPI``.
"""

from bitmath import GiB, Byte
from zope.interface import implementer
import requests
from oauth2client.gce import AppAssertionCredentials
from googleapiclient import discovery
from googleapiclient.errors import HttpError
from socket import gethostname
from uuid import UUID

from .blockdevice import (
    IBlockDeviceAPI, BlockDeviceVolume, AlreadyAttachedVolume, UnknownVolume
)
from ...common import poll_until

# GCE instances have a metadata server that can be queried for information
# about the instance the code is being run on.
_METADATA_SERVER = u'http://169.254.169.254/computeMetadata/v1/'
_METADATA_HEADERS = {u'Metadata-Flavor': u'Google'}


def _get_metadata_path(path):
    """
    Requests a metadata path from the metadata server available within GCE.
    """
    timeout_sec = 3
    r = requests.get(_METADATA_SERVER + path,
                     headers=_METADATA_HEADERS,
                     timeout=timeout_sec)
    return r.text

_PREFIX='flocker-'

def _blockdevice_id_to_dataset_id(blockdevice_id):
    return UUID(blockdevice_id[len(_PREFIX):])

def _dataset_id_to_blockdevice_id(dataset_id):
    return _PREFIX + unicode(dataset_id)


def _extract_attached_to(val):
    if not val:
        return None
    return unicode(val[0].split('/')[-1])


@implementer(IBlockDeviceAPI)
class PDBlockDeviceAPI(object):
    """
    A PD implementation of ``IBlockDeviceAPI`` which creates block devices in a
    GCE project.
    """

    def __init__(self, project, zone):
        """
        """
        credentials = AppAssertionCredentials(
            "https://www.googleapis.com/auth/cloud-platform")
        self._compute = discovery.build(
            'compute', 'v1', credentials=credentials)
        self._project = project
        self._zone = zone

    def _do_blocking_operation(self, function, **kwargs):
        args = dict(project=self._project, zone=self._zone)
        args.update(kwargs)
        operation = function(**args).execute()
        operation_name = operation['name']

        def finished_operation_result():
            latest_operation = self._compute.zoneOperations().get(
                project=self._project,
                zone=self._zone,
                operation=operation_name).execute()
            print "BREAK"
            print latest_operation
            if latest_operation['status'] == 'DONE':
                return latest_operation
            return None

        # TODO(mewert): Collect data or look at EBS to figure out good values
        # of retries.
        return poll_until(finished_operation_result, [1]*20)

    def allocation_unit(self):
        """
        Can only allocate PDs in GiB units.
        """
        return int(GiB(1).to_Byte().value)

    def list_volumes(self):
        #TODO(mewert) there be pages here
        #TODO(mewert) only get volumes for _this_ cluster.
        result = self._compute.disks().list(project=self._project,
                                            zone=self._zone).execute()
        return list(
            BlockDeviceVolume(
                blockdevice_id=unicode(x['name']),
                size=int(GiB(int(x['sizeGb'])).to_Byte()),
                attached_to=_extract_attached_to(x['users']),
                dataset_id=_blockdevice_id_to_dataset_id(x['name'])
            )
            for x in result['items']
            if x['name'].startswith(_PREFIX)
        )


    def compute_instance_id(self):
        return unicode(gethostname())

    def create_volume(self, dataset_id, size):
        blockdevice_id = _dataset_id_to_blockdevice_id(dataset_id)
        sizeGiB=int(Byte(size).to_GiB())
        config = dict(
            name=blockdevice_id,
            sizeGb=sizeGiB
        )
        result = self._do_blocking_operation(
            self._compute.disks().insert, body=config)
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
            result = self._do_blocking_operation(
                self._compute.instances().attachDisk,
                instance=attach_to,
                body=config
            )
        except HttpError e:
            print e
            import pdb; pdb.set_trace
            raise UnknownVolume(blockdevice_id)
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

    def detach_volume(self, blockdevice_id):
        disk = self._compute.disks().get(project=self._project,
                                         zone=self._zone,
                                         disk=blockdevice_id).execute()
        attached_to = _extract_attached_to(disk['users'])
        if attached_to:
            result = self._do_blocking_operation(
                self._compute.instances().detachDisk, instance=attached_to,
                deviceName=blockdevice_id)
        return None

    def get_device_path(self, blockdevice_id):
        return u"/dev/disk/by-id/google-" + blockdevice_id

    def destroy_volume(self, blockdevice_id):
        self._do_blocking_operation(
            self._compute.disks().delete,
            disk=blockdevice_id
        )
        return None
