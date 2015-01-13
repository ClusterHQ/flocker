# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
DigitalOcean provisioner.
"""

from ._libcloud import LibcloudProvisioner
from ._install import (
    provision, run,
    task_install_ssh_key,
    task_upgrade_kernel,
    task_upgrade_selinux,
)

def provision_digitalocean(node, package_source, distribution):
    """
    Provision flocker on this node.
    """
    import pdb; pdb.set_trace()
    # DO doesn't support booting the droplet's own kernel.
    # * http://digitalocean.uservoice.com/forums/136585-digitalocean/suggestions/2814988-give-option-to-use-the-droplet-s-own-bootloader
    # So rather than upgrade, we'll need to have new task to install the kernel
    # package (and headers) for the DO supported kernel.
    # The Fedora droplet default is to use a kernel that's too old for our purposes.
    # Our documentation describes how to select a newer (DO supported) kernel for this droplet.
    # Unfortunately it looks like this operation is only supported in the DO v2 API.
    # * http://digitalocean.uservoice.com/forums/136585-digitalocean/suggestions/5618546-add-the-ability-to-change-kernel-via-api
    # * https://developers.digitalocean.com/#change-the-kernel
    # But libcloud only supports the DO v1 API
    # * https://www.digitalocean.com/community/questions/does-libcloud-work-with-digitalocean-s-v2-api
    # XXX: Double check this.
    # run(
    #     username='root',
    #     address=node.address,
    #     commands=task_upgrade_kernel(),
    # )

    # Need to power cycle instead.
    # Create a new task to shutdown the machine
    # Then make an API call to boot it up again.
    # XXX: Check whether this still applies if we use the kexec method above.
    # node.reboot()

    # This may not be necessary with the DO Fedora distribution.
    # run(
    #     username='root',
    #     address=node.address,
    #     commands=task_upgrade_selinux(),
    # )

    # Finally run all the standard Fedora20 installation steps.
    # run(
    #     username='root',
    #     address=node.address,
    #     commands=provision(
    #         package_source=package_source,
    #         distribution=node.distribution,
    #     )
    # )
    return node.address


# Figure out which image names are supported by DO
# http://doc-dev.clusterhq.com/gettingstarted/installation.html#using-digitalocean
# (Pdb++) print '\n'.join('%r' % ((i.id, i.name, i.extra),) for i in driver.list_images())
# ...
# ('9836782', u'557.0.0 (alpha)', {'distribution': u'CoreOS'})
# ('9836871', u'522.4.0 (beta)', {'distribution': u'CoreOS'})
# ('9836874', u'522.4.0 (stable)', {'distribution': u'CoreOS'})
# ('6370882', u'20 x64', {'distribution': u'Fedora'})
# ('6370968', u'19 x64', {'distribution': u'Fedora'})
# ('6372108', u'6.5 x64', {'distribution': u'CentOS'})
# ('6372321', u'5.10 x64', {'distribution': u'CentOS'})
# ('6372526', u'7.0 x64', {'distribution': u'Debian'})
# ('6372581', u'6.0 x64', {'distribution': u'Debian'})
# ('6374124', u'10.04 x64', {'distribution': u'Ubuntu'})
# ('6374128', u'12.04.5 x64', {'distribution': u'Ubuntu'})
# ('7053293', u'7.0 x64', {'distribution': u'CentOS'})
# ('9801950', u'14.04 x64', {'distribution': u'Ubuntu'})
# ('9801954', u'14.10 x64', {'distribution': u'Ubuntu'})
IMAGE_NAMES = {
    # It'd be better to use image ID here, but the following code is currently
    # written to lookup image names...which would normally be good for
    # readability but which in the case DigitalOcean are pretty meaningless.
     'fedora-20': '20 x64',
}


def get_location(driver, location_id):
    """
    Return a ``NodeLocation`` corresponding to a given id.

    XXX: Find out if DigitalOcean Locations have short human readable labels
    instead. The webui shows eg lon1 and ams3 so I guess it's possible.

    :param driver: The libcloud driver to query for sizes.
    """
    try:
        return [l for l in driver.list_locations() if l.id == location_id][0]
    except IndexError:
        raise ValueError("Unknown location.", location_id)


def get_ssh_key_id(driver, ssh_key_name):
    """
    """
    # There's no high level API for this in the DigitalOcean driver.
    response = driver.connection.request('/ssh_keys')
    keys = response.object['ssh_keys']
    try:
        return [k['id'] for k in keys if k['name'] == ssh_key_name][0]
    except IndexError:
        raise ValueError("Unknown SSH keyname.", ssh_key_name)


def digitalocean_provisioner(client_id, api_key, location_id, keyname):
    """
    Create a LibCloudProvisioner for provisioning nodes on DigitalOcean.

    :param bytes access_key: The access_key to connect to AWS with.
    :param bytes secret_access_token: The corresponding secret token.
    :param bytes region: The AWS region in which to launch the instance.
    :param bytes keyname: The name of an existing ssh public key configured in
       AWS. The provision step assumes the corresponding private key is
       available from an agent.
    :param list security_groups: List of security groups to put created nodes
        in.
    """
    # Import these here, so that this can be imported without
    # installing libcloud.
    from libcloud.compute.providers import get_driver, Provider

    driver_factory = get_driver(Provider.DIGITAL_OCEAN)
    driver = driver_factory(key=client_id, secret=api_key)

    def create_arguments(disk_size):
        """
        :param disk_size: Unused
        """
        return {
            "location": get_location(driver, location_id),
            # XXX: DigitalOcean driver doesn't use the standard ex_keyname
            # parameter. Perhaps ``_libcloud.LibcloudProvisioner.create_node
            # needs refactoring.
            "ex_ssh_key_ids": [str(get_ssh_key_id(driver, keyname))]
        }

    provisioner = LibcloudProvisioner(
        driver=driver,
        keyname=keyname,
        image_names=IMAGE_NAMES,
        create_node_arguments=create_arguments,
        provision=provision_digitalocean,
        # The NodeSize repr suggests that ``id`` is an ``int`` but in fact it's a string.
        # Perhaps we need to modify _libcloud.get_size or something.
        # <NodeSize: id=65, name=8GB, ram=8192 disk=0 bandwidth=0 price=0 driver=Digital Ocean ...>
        default_size="65",
    )

    return provisioner
