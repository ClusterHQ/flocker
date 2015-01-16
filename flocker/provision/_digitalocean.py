# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
DigitalOcean provisioner.
"""
import time
from functools import partial

import pyocean

from ._libcloud import LibcloudProvisioner
from ._install import (
    provision, run,
    task_install_kernel,
)


def retry_if_pending(callable, *args, **kwargs):
    """
    DigitalOceanV2 API only allows one change at a time and returns HTTP code
    402 if another change is already pending.

    So this function repeats the API call if that error code is received and
    returns the result if the call eventually succeeds.

    The raw DO API returns ``event``s whose status can be queried, and that
    would be a better way to block before issuing the next API call, but
    pyocean doesn't consistently return the event info. E.g. droplet.create
    returns a ``droplet`` instance instead whose status is difficult to check.

    See https://digitalocean.uservoice.com/forums/136585-digitalocean/suggestions/4842992-allow-api-calls-to-queue-rather-than-just-rejectin # noqa

    :param callable: The API function to call.
    :param args: Positional arguments to supply when calling it.
    :param kwargs: Keyword arguments to supply when calling it.
    :return: The result of calling  ``callable``.
    """
    while True:
        try:
            result = callable(*args, **kwargs)
        except pyocean.exceptions.ClientError as e:
            if e.message == 'Droplet already has a pending event.':
                time.sleep(1)
                continue
            raise
        else:
            return result


def set_latest_droplet_kernel(droplet, kernel_prefix='Fedora 20 x64'):
    """
    Change the kernel of the droplet with ``droplet_id`` to the latest kernel
    version with the given ``kernel_prefix``.

    :param ``pyocean.Droplet`` droplet: The droplet whose kernel will be
        configured.
    :param bytes kernel_prefix: Only kernel names with this prefix will be
        considered.
    :returns: A ``pyocean.Kernel`` instance which was assigned to the droplet.
    """
    matching_kernels = [kernel for kernel in droplet.get_available_kernels()
                        if kernel.name.startswith(kernel_prefix)]
    latest_kernel = sorted(
        matching_kernels,
        key=lambda kernel: kernel.version.split('.'),
        reverse=True)[0]

    retry_if_pending(droplet.change_kernel, latest_kernel.id)
    return latest_kernel


def provision_digitalocean(node, package_source, distribution, token):
    """
    Provision flocker on this node.
    """
    # DO doesn't support booting the droplet's own kernel.
    # * http://digitalocean.uservoice.com/forums/136585-digitalocean/suggestions/2814988-give-option-to-use-the-droplet-s-own-bootloader # noqa
    # So rather than upgrade, we'll need to have new task to install the kernel
    # package (and headers) for the DO supported kernel.
    # The Fedora droplet default is to use a kernel that's too old for our
    # purposes.
    # Our documentation describes how to select a newer (DO supported) kernel
    # for this droplet.
    # Unfortunately this operation is only supported in the DO v2 API.
    # * http://digitalocean.uservoice.com/forums/136585-digitalocean/suggestions/5618546-add-the-ability-to-change-kernel-via-api # noqa
    # * https://developers.digitalocean.com/#change-the-kernel
    # But libcloud only supports the DO v1 API
    # * https://www.digitalocean.com/community/questions/does-libcloud-work-with-digitalocean-s-v2-api # noqa
    # * https://issues.apache.org/jira/browse/JCLOUDS-613
    v2client = pyocean.DigitalOcean(access_token=token)
    v2droplet = v2client.droplet.get(node._node.id)

    kernel = set_latest_droplet_kernel(v2droplet)
    version, distribution, architecture = kernel.version.rsplit('.', 2)
    version, release = version.split('-', 1)
    run(
        username='root',
        address=node.address,
        commands=task_install_kernel(version=version, release=release,
                                     distribution='fc20',
                                     architecture='x86_64')
    )

    # Libcloud doesn't support shutting down DO vms.
    # See https://issues.apache.org/jira/browse/LIBCLOUD-655
    retry_if_pending(v2droplet.shutdown)

    # Sorry about this, but shutdown returns the following, indicating that the
    # droplet has halted, but it still seems to require some time before
    # powering on.
    # {u'status': u'completed', u'resource_id': 3797602, u'region': u'ams3', u'completed_at': u'2015-01-15T20:52:36Z', u'started_at': u'2015-01-15T20:52:31Z', u'type': u'shutdown', u'id': 41364967, u'resource_type': u'droplet'} # noqa
    time.sleep(30)

    # Libcloud doesn't support powering up DO vms.
    # See https://issues.apache.org/jira/browse/LIBCLOUD-655
    retry_if_pending(v2droplet.power_on)

    # Finally run all the standard Fedora20 installation steps.
    run(
        username='root',
        address=node.address,
        commands=provision(
            package_source=package_source,
            distribution=node.distribution,
        )
    )
    return node.address


IMAGE_NAMES = {
    # It'd be better to use image ID here, but the following code is currently
    # written to lookup image names...which would normally be good for
    # readability but which in the case DigitalOcean are pretty meaningless.
    'fedora-20': '20 x64',
}


def location_by_slug(driver, location_slug):
    """
    Look up a DigitalOcean location by its short human readable "slug" code.

    # XXX: ``libcloud.DigitalOceanDriver.list_locations`` discards the slug
    # so we make a direct call to the v1 API and parse the returned dictionary.
    # See https://issues.apache.org/jira/browse/LIBCLOUD-653

    :param driver: The libcloud driver to query for sizes.
    :param bytes location_slug: A DigitalOcean location "slug".
    :returns: ``NodeLocation``.
    """
    result = driver.connection.request('/regions')
    for location_dict in result.object['regions']:
        if location_dict['slug'] == location_slug:
            break
    else:
        raise ValueError("Unknown location slug.", location_slug)

    return driver._to_location(location_dict)


def size_by_slug(driver, size_slug):
    """
    Look up a DigitalOcean size by its short human readable "slug" code.

    # XXX: ``libcloud.DigitalOceanDriver.list_sizes`` discards the slug
    # so we make a direct call to the v1 API and parse the returned dictionary.
    # See https://issues.apache.org/jira/browse/LIBCLOUD-654

    :param driver: The libcloud driver to query for sizes.
    :param bytes size_slug: A DigitalOcean size "slug".
    :returns: ``NodeSize``.
    """
    result = driver.connection.request('/sizes')
    for size_dict in result.object['sizes']:
        if size_dict['slug'] == size_slug:
            break
    else:
        raise ValueError("Unknown size slug.", size_slug)

    return driver._to_size(size_dict)


def ssh_key_by_name(driver, ssh_key_name):
    """
    Return the ``SSHKey`` with the given name.

    :param DigitalOceanDriver driver: The driver to use for issuing queries.
    :param bytes ssh_key_name: The name of a registered SSH key.
    :returns: ``SSHKey``
    """
    for ssh_key in driver.ex_list_ssh_keys():
        if ssh_key.name == ssh_key_name:
            break
    else:
        raise ValueError("Unknown SSH key name.", ssh_key_name)

    return ssh_key


def digitalocean_provisioner(client_id, api_key, token, location, keyname):
    """
    Create a LibCloudProvisioner for provisioning nodes on DigitalOcean.

    :param bytes client_id: A V1 API client ID.
    :param bytes api_key: A V1 API key.
    :param bytes token: A V2 API token.
    :param bytes location: The slug for the location in which new nodes will be
        created.
    :param bytes keyname: The name of an existing ssh public key configured in
       DigitalOcean. The provision step assumes the corresponding private key
       is available from an agent.
    """
    # Import these here, so that this can be imported without
    # installing libcloud.
    from libcloud.compute.providers import get_driver, Provider

    driver_factory = get_driver(Provider.DIGITAL_OCEAN)
    driver = driver_factory(key=client_id, secret=api_key)
    ssh_key = ssh_key_by_name(driver, keyname)
    size = size_by_slug(driver, "8gb")

    def create_arguments(disk_size):
        """
        :param disk_size: DigitalOcean doesn't support arbitrary disk sizes.
        """
        return {
            "location": location_by_slug(driver, location),
            # XXX: DigitalOcean driver doesn't use the standard ex_keyname
            # See https://clusterhq.atlassian.net/browse/FLOC-1228
            "ex_ssh_key_ids": [str(ssh_key.id)]
        }

    provisioner = LibcloudProvisioner(
        driver=driver,
        keyname=keyname,
        image_names=IMAGE_NAMES,
        create_node_arguments=create_arguments,
        # Tack the token on here because its not a standard part of the API.
        provision=partial(provision_digitalocean, token=token),
        default_size=size.id,
    )

    return provisioner
