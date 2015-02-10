# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
DigitalOcean provisioner.
"""
import time
from functools import partial

from ._libcloud import LibcloudProvisioner
from ._install import (
    provision, run,
    task_install_digitalocean_kernel, DIGITALOCEAN_KERNEL
)
from ._common import Kernel


def retry_on_error(error_checkers, callable, *args, **kwargs):
    """
    This function repeats the API call if it raises an exception and if that
    exception is validated by any of the supplied checkers.
    It returns the result if the call eventually succeeds.

    :param error_checkers: A ``list`` of ``callables`` which will check for
        expected exceptions.
    :param callable: The API function to call.
    :param args: Positional arguments to supply when calling it.
    :param kwargs: Keyword arguments to supply when calling it.
    :return: The result of calling  ``callable``.
    """
    while True:
        try:
            result = callable(*args, **kwargs)
        except Exception as e:
            for checker in error_checkers:
                if checker(e):
                    time.sleep(1)
                    break
            else:
                raise
        else:
            return result


def pending_event(exception):
    """
    Check for a pending event exception.

    DigitalOceanV2 API only allows one change at a time and returns HTTP code
    402 if another change is already pending.

    So this function repeats the API call if that error code is received and
    returns the result if the call eventually succeeds.

    The raw DO API returns ``event``s whose status can be queried, and that
    would be a better way to block before issuing the next API call, but
    pyocean doesn't consistently return the event info. E.g. droplet.create
    returns a ``droplet`` instance instead whose status is difficult to check.

    See https://digitalocean.uservoice.com/forums/136585-digitalocean/suggestions/4842992-allow-api-cal # noqa

    :param Exception exception: The exception that will be checked for type and
        message
    :return: ``True`` if ``exception`` matches else ``False``.
    """
    # Import here, so that this can be added to ``flocker.provision`` without
    # having to install ``pyocean``.
    import pyocean

    if isinstance(exception, pyocean.exceptions.ClientError):
        if exception.message == 'Droplet already has a pending event.':
            return True
    return False


def droplet_still_on(exception):
    """
    Check for a droplet still on exception.

    Shutdown returns the following event, indicating that the
    droplet has halted.

    {u'completed_at': u'2015-01-15T20:52:36Z',
     u'id': 41364967,
     u'region': u'ams3',
     u'resource_id': 3797602,
     u'resource_type': u'droplet',
     u'started_at': u'2015-01-15T20:52:31Z',
     u'status': u'completed',
     u'type': u'shutdown'}

    But it still seems to require some time before powering on, so catch the
    "currently on" exception and retry in that case.

    :param Exception exception: The exception that will be checked for type and
        message
    :return: ``True`` if ``exception`` matches else ``False``.
    """
    # Import here, so that this can be added to ``flocker.provision`` without
    # having to install ``pyocean``.
    import pyocean

    if (isinstance(exception, pyocean.exceptions.ClientError)
        and exception.message == ('Droplet is currently on. '
                                  'Please power it off to run this event.')):
        return True
    return False


def kernel_from_digitalocean_version(version):
    """
    Parse a DigitalOcean kernel version string into its component parts.

    :param bytes version: The DigitalOcean kernel version string.
    :return: ``Kernel`` with version information.
    """
    version, remaining = version.split('-', 1)
    release, distribution, architecture = remaining.split('.', 2)
    return Kernel(
        version=version,
        release=release,
        distribution=distribution,
        architecture=architecture
    )


DIGITAL_OCEAN_KERNEL_VERSION_TEMPLATE = (
    '{version}-{release}.{distribution}.{architecture}'
)


def kernel_to_digitalocean_version(kernel):
    """
    Return a DigitalOcean style kernel string for the supplied ``Kernel``.

    :param Kernel kernel: The ``Kernel`` from which to get attributes for
        filling the template.
    :returns: A ``bytes`` DigitalOcean kernel label.
    """
    return DIGITAL_OCEAN_KERNEL_VERSION_TEMPLATE.format(
        version=kernel.version,
        release=kernel.release,
        distribution=kernel.distribution,
        architecture=kernel.architecture
    )


def get_droplet_kernel(droplet, required_kernel):
    """
    Search a droplet for a certain kernel and return a ``pyocean.Kernel`` which
    can then be used to reset the droplet's kernel.

    :param Kernel required_kernel: The kernel version to search for.
    :returns: A ``pyocean.Kernel`` instance corresponding to the supplied
        ``required_kernel``.
    """
    full_version = kernel_to_digitalocean_version(required_kernel)
    for do_kernel in droplet.get_available_kernels():
        if do_kernel.version == full_version:
            return do_kernel
    else:
        raise ValueError('Unknown kernel', required_kernel)


def latest_droplet_kernel(droplet,
                          required_distribution, required_architecture):
    """
    Return the newest kernel available for the supplied droplet, with the given
    distribution and architecture.

    :param required_distribution: Only look for kernels for this distribution.
    :param required_architecture: Only look for kernels for this architecture.
    :return: A ``Kernel`` with the latest version information.
    """
    matching_kernels = []
    for do_kernel in droplet.get_available_kernels():
        kernel = kernel_from_digitalocean_version(do_kernel.version)

        if ((required_distribution,
             required_architecture) == (kernel.distribution,
                                        kernel.architecture)):
            matching_kernels.append(kernel)

    if not matching_kernels:
        raise ValueError(
            'No kernels for required distribution and architecture',
            required_distribution, required_architecture)

    latest_kernel = sorted(
        matching_kernels,
        key=lambda kernel: (kernel.version_tuple, kernel.release),
        reverse=True)[0]

    return latest_kernel


def provision_digitalocean(node, package_source, distribution, token):
    """
    Provision Flocker on this node.

    :param LibcloudNode node: The node to be provisioned.
    :param PackageSource package_source: The URL of the distribution package
        repository.
    :param bytes distribution: The label of the distribution to be installed on
        the node.
    :param bytes token: A DigitalOcean v2 API token.
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

    # Import here, so that this can be added to ``flocker.provision`` without
    # having to install ``pyocean``.
    import pyocean

    v2client = pyocean.DigitalOcean(access_token=token)
    v2droplet = v2client.droplet.get(node._node.id)
    do_kernel = get_droplet_kernel(v2droplet, DIGITALOCEAN_KERNEL)

    retry_on_error(
        [pending_event],
        v2droplet.change_kernel, do_kernel.id)

    run(
        username='root',
        address=node.address,
        commands=task_install_digitalocean_kernel()
    )

    # Libcloud doesn't support shutting down DO vms.
    # See https://issues.apache.org/jira/browse/LIBCLOUD-655
    retry_on_error(
        [pending_event],
        v2droplet.shutdown)

    # Libcloud doesn't support powering up DO vms.
    # See https://issues.apache.org/jira/browse/LIBCLOUD-655
    # Even after the shutdown, the droplet may not be quite ready to power on,
    # so also check for that resulting error here.
    retry_on_error([pending_event, droplet_still_on], v2droplet.power_on)

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
            return driver._to_size(size_dict)
    else:
        raise ValueError("Unknown size slug.", size_slug)


def ssh_key_by_name(driver, ssh_key_name):
    """
    Return the ``SSHKey`` with the given name.

    :param DigitalOceanDriver driver: The driver to use for issuing queries.
    :param bytes ssh_key_name: The name of a registered SSH key.
    :returns: ``SSHKey``
    """
    for ssh_key in driver.ex_list_ssh_keys():
        if ssh_key.name == ssh_key_name:
            return ssh_key
    else:
        raise ValueError("Unknown SSH key name.", ssh_key_name)


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
        :param int disk_size: Unused. DigitalOcean doesn't support arbitrary
            disk sizes.
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
