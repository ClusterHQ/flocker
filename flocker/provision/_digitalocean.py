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
    # I don't think this step will be necessary. DO installs the SSH keys for
    # root automatically.
    # run(
    #     username='fedora',
    #     address=node.address,
    #     commands=task_install_ssh_key(),
    # )

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
    # So we may be forced to make direct REST API calls here instead.
    # Or use the kexec trick described by Richard Yao:
    # * https://zulip.com/#narrow/stream/social/topic/How.20to.20fix.20a.20Fedora.20VM.20running.20at.20Digital.20Ocean
    # yum update -y
    # KV=$(rpm -q kernel | sed 's/kernel-//' | sort --general-numeric-sort | tail -n 1)
    # yum install -y kexec-tools kernel-headers-${KV}
    # kexec -l /boot/vmlinuz-${KV} --initrd=/boot/initramfs-${KV}.img --command-line="root=$(df --output=source /boot | sed '1d') ro"
    # echo u > /proc/sysrq-trigger
    # kexec -e
    # ...and turn that into a task which can be included in the documentation.
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
IMAGE_NAMES = {
#     'fedora-20': 'Fedora-x86_64-20-20140407-sda',
}

def digitalocean_provisioner(client_id, api_key, location_id):
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

    import pdb; pdb.set_trace()

    def create_arguments(disk_size):
        """
        :param disk_size: Unused
        """
        return {
            "location": location_id,
            # A list of ssh key ids which will be added to the server.
            "ex_ssh_key_ids": None
        }

    provisioner = LibcloudProvisioner(
        driver=driver,
        keyname=keyname,
        image_names=IMAGE_NAMES,
        create_node_arguments=create_arguments,
        provision=provision_digitalocean,
        # Find out which droplet sizes DO supports and their codes.
        default_size="m3.large",
    )

    return provisioner
