# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
GCE provisioner.

The following resources are helpful to refer to while maintaining this file:
- Rest API: https://cloud.google.com/compute/docs/reference/latest/
- Python Client: https://cloud.google.com/compute/docs/tutorials/python-guide
- Python API: https://google-api-client-libraries.appspot.com/documentation/compute/v1/python/latest/ # noqa
- Python Oauth: https://developers.google.com/identity/protocols/OAuth2ServiceAccount#authorizingrequests # noqa

We store the metadata as a JSON blob in the description of the instance.

A convenient ``jq`` blob for seeing the list of all nodes created by this
provisioner, and unwinding the encoded description is:

    gcloud compute instances list --format=json | jq '.[] |
        select(.tags.items | [.[]?] | map(. == "json-description") | any) |
        setpath(["description"]; .description|fromjson)'
"""

from pyrsistent import PClass, field
from twisted.conch.ssh.keys import Key
from zope.interface import implementer
from googleapiclient import discovery
from oauth2client.client import GoogleCredentials

from ._common import IProvisioner

from ..node.agents.gce import wait_for_operation

import json


# Defaults for some of the instance construction parameters.
_GCE_DISK_SIZE_GIB = 10
_GCE_INSTANCE_TYPE = u"n1-standard-1"
_GCE_ACCEPTANCE_USERNAME = u"flocker-acceptance"


def _clean_to_gce_name(identifier):
    """
    GCE requires the names of all resources to comply with RFC1035. This
    function takes an identifier which might not comply with RFC1035 and
    attempts to map it into the logical equivalent identifier that does match
    RFC1035.

    :param unicode identifier: The input identifier to be mapped into something
        RFC1035 compliant.

    :returns: An RFC1035 compliant variation of the identifier.
    """
    return identifier.lower().replace(u'+', u'-')


class _DistributionImageParams(PClass):
    """
    Simple helper to discover the latest available image for a given
    distribution. See the docstring for :func:`get_active_image` for an
    explanation of the GCE image system.

    :ivar unicode project: The name of the project to search for a specific image.
    :ivar unicode image_name_prefix: The prefix of the image to find.
    """
    project = field(type=unicode)
    image_name_prefix = field(type=unicode)

    def get_active_image(self, compute):
        """
        Gets a non-deprecated image from a project with a given prefix.

        The images provided by gce go in distribution-specific projects, but are
        publicly accessible by anyone.

        For example, all ubuntu images are in the ``ubuntu-os-cloud`` project. In
        that project there is only 1 non-deprecated image for the various ubuntu
        versions (1 for ubuntu 14.04, 1 for ubuntu 15.10, etc). There are also many
        deprecated versions, which were marked as deprecated when the new one was
        created (for security updates, etc.). All of the 14.04 images are named
        ubuntu-1404-trusty-vYYYYMMDD?. So, searching the ``ubuntu-os-cloud``
        project for a non-deprecated image with the ``ubuntu-1404`` prefix is a
        reasonable way to find the latest ubuntu 14.04 image.

        The best way to get a list of possible ``image_name_prefix`` values is to
        look at the output from ``gcloud compute images list``

        If you don't have the gcloud executable installed, it can be pip installed:
        ``pip install gcloud``

        project, image_name_prefix examples:
        * ubuntu-os-cloud, ubuntu-1404
        * centos-cloud, centos-7

        :param compute: The Google Compute Engine Service object used to make calls
            to the GCE API.

        :returns: The image resource dict representing the GCE image resource, or
            None if no image found.
        """
        latest_image = None
        page_token = None
        while not latest_image:
            response = compute.images().list(
                project=self.project,
                maxResults=500,
                pageToken=page_token,
                # Filter can be a regex.
                filter='name eq {}.*'.format(self.image_name_prefix)
            ).execute()

            latest_image = next((image for image in response.get('items', [])
                                if 'deprecated' not in image),
                                None)
            page_token = response.get('nextPageToken')
            if not page_token:
                break
        return latest_image


# Parameters to find the active image for a given distribution.
_GCE_DISTRIBUTION_TO_IMAGE_MAP = {
    u"centos-7": _DistributionImageParams(
        project=u"centos-cloud",
        image_name_prefix=u"centos-7",
    ),
    u"ubuntu-14.04": _DistributionImageParams(
        project=u"ubuntu-os-cloud",
        image_name_prefix=u"ubuntu-1404",
    )
}


def _create_gce_instance_config(instance_name, project, zone, machine_type,
                                image, username, public_key, disk_size,
                                description, tags, delete_disk_on_terminate):
    """
    Create a configuration blob to configure a GCE instance.

    :param unicode instance_name: The name of the instance.
    :param unicode project: The name of the gce project to create a configuration for.
    :param unicode zone: The name of the gce zone to spin the instance up in.
    :param unicode machine_type: The name of the machine type, e.g. 'n1-standard-1'.
    :param unicode image: The name of the image to base the disk off of.
    :param unicode username: The username of user to create on the vm.
    :param unicode public_key: The public ssh key to put on the image for the
        given username.
    :param int disk_size: The size of the disk to create, in GiB.
    :param unicode description: The description to set on the instance.
    :param set tags: A set of unicode tags to apply to the image.
    :param bool delete_disk_on_terminate: Whether to delete the disk when the
        instance terminates or not.

    :return: A dictionary that can be consumed by the `googleapiclient` to
        insert an instance.
    """
    gce_slave_instance_config = {
        u"name": unicode(instance_name),
        u"machineType": (
            u"projects/{}/zones/{}/machineTypes/{}".format(
                project, zone, machine_type)
            ),
        u"disks": [
            {
                u"type": u"PERSISTENT",
                u"boot": True,
                u"mode": u"READ_WRITE",
                u"autoDelete": delete_disk_on_terminate,
                u"initializeParams": {
                    u"sourceImage": unicode(image),
                    u"diskType": (
                        u"projects/{}/zones/{}/diskTypes/pd-standard".format(
                            project, zone)
                    ),
                    u"diskSizeGb": unicode(disk_size)
                }
            }
        ],
        u"networkInterfaces": [
            {
                u"network": (
                    u"projects/{}/global/networks/default".format(project)
                ),
                u"accessConfigs": [
                    {
                        u"name": u"External NAT",
                        u"type": u"ONE_TO_ONE_NAT"
                    }
                ]
            }
        ],
        u"metadata": {
            u"items": [
                {
                    u"key": u"sshKeys",
                    u"value": u"{}:{}".format(username, public_key)
                }
            ]
        },
        u"description": description,
        u"serviceAccounts": [
            {
                u"email": u"default",
                u"scopes": [
                    # This gives the image permission to do GCE api calls (like
                    # creating and attaching block devices) with its built-in
                    # service account
                    u"https://www.googleapis.com/auth/compute",
                ]
            }
        ],
        u"tags": {
            u"items": list(
                tag for tag in tags
            )
        }
    }
    return gce_slave_instance_config


@implementer(IProvisioner)
class GCEProvisioner(PClass):
    """
    A provisioner that can create instances on GCE.

    :ivar unicode zone: The zone in which instances will be provisioned in.
    :ivar unicode project: The project under which instances will be
        provisioned in.
    :ivar Key ssh_public_key: The public ssh key that will transferred to the
        instance for access.
    :ivar compute: A Google Compute Engine Service that can be used to make
        calls to the GCE API.
    """

    zone = field(type=unicode)
    project = field(type=unicode)
    ssh_public_key = field(type=Key)
    compute = field()

    def get_ssh_key(self):
        return self.ssh_public_key

    def create_node(self, name, distribution, metadata={}):
        config = _create_gce_instance_config(
          instance_name=_clean_to_gce_name(name),
          project=self.project,
          zone=self.zone,
          machine_type=_GCE_INSTANCE_TYPE,
          image=_GCE_DISTRIBUTION_TO_IMAGE_MAP[distribution].get_active_image(
              self.compute
          )["selfLink"],
          username=_GCE_ACCEPTANCE_USERNAME,
          public_key=self.ssh_public_key.toString('OPENSSH'),
          disk_size=_GCE_DISK_SIZE_GIB,
          description=json.dumps({
              u"description-format": u"v1",
              u"created-by-python": u"flocker.provision._gce.GCEProvisioner",
              u"name": name,
              u"metadata": metadata
          }),
          tags=set([u"flocker-gce-provisioner", u"json-description"]),
          delete_disk_on_terminate=True
        )

        operation = self.compute.instances().insert(
            project=self.project,
            zone=self.zone,
            body=config
        ).execute()

        operation_result = wait_for_operation(self.compute, operation, timeout=60)
        print operation_result


def gce_provisioner(
    zone, project, ssh_public_key
):
    """
    Create an :class:`IProvisioner` for provisioning nodes on GCE.

    :param unicode zone: The name of the zone in which to provision instances.
    :param unicode project: The name of the project in which to provision
        instances.
    :param unicode ssh_public_key: The public key that will be put on the VM
        for ssh access.

    :return: An class:`IProvisioner` provider for GCE instances.
    """
    key = Key.fromString(bytes(ssh_public_key))
    credentials = GoogleCredentials.get_application_default()
    compute = discovery.build('compute', 'v1', credentials=credentials)

    return GCEProvisioner(
        zone=unicode(zone),
        project=unicode(project),
        ssh_public_key=key,
        compute=compute,
    )
