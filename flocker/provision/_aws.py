# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
AWS provisioner.
"""

from ._libcloud import LibcloudProvisioner
from ._common import Variants
from ._install import (
    provision, run,
    task_install_ssh_key,
    task_upgrade_kernel,
    task_upgrade_selinux,
    task_enable_updates_testing
)


def provision_aws(node, package_source, distribution, variants):
    """
    Provision flocker on this node.
    """
    run(
        username='fedora',
        address=node.address,
        commands=task_install_ssh_key(),
    )

    if Variants.DISTRO_TESTING in variants:
        # FIXME: We shouldn't need to duplicate this here.
        run(
            username='root',
            address=node.address,
            commands=task_enable_updates_testing(distribution)
        )

    run(
        username='root',
        address=node.address,
        commands=task_upgrade_kernel(),
    )

    node.reboot()

    run(
        username='root',
        address=node.address,
        commands=provision(
            package_source=package_source,
            distribution=node.distribution,
            variants=variants,
        ) + task_upgrade_selinux(),
    )
    return node.address


IMAGE_NAMES = {
    'fedora-20': 'Fedora-x86_64-20-20140407-sda',
}


def aws_provisioner(access_key, secret_access_token, keyname,
                    region, security_groups):
    """
    Create a LibCloudProvisioner for provisioning nodes on AWS EC2.

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
    # installng libcloud.
    from libcloud.compute.providers import get_driver, Provider
    driver = get_driver(Provider.EC2)(
        key=access_key,
        secret=secret_access_token,
        region=region)

    def create_arguments(disk_size):
        return {
            "ex_securitygroup": security_groups,
            "ex_blockdevicemappings": [
                {"DeviceName": "/dev/sda1",
                 "Ebs": {"VolumeSize": disk_size,
                         "DeleteOnTermination": True,
                         "VolumeType": "gp2"}}
            ],
        }

    provisioner = LibcloudProvisioner(
        driver=driver,
        keyname=keyname,
        image_names=IMAGE_NAMES,
        create_node_arguments=create_arguments,
        provision=provision_aws,
        default_size="m3.large",
    )

    return provisioner
