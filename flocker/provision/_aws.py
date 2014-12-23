# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
AWS provisioner.
"""

from ._libcloud import LibcloudProvisioner
from ._install import (
    provision, run_with_fabric,
    task_install_ssh_key,
    task_upgrade_kernel,
    task_upgrade_selinux,
)


def provision_aws(node, package_source, distribution):
    """
    Provision flocker on this node.
    """
    run_with_fabric(
        username='fedora',
        address=node.address,
        commands=task_install_ssh_key(),
    )
    run_with_fabric(
        username='root',
        address=node.address,
        commands=task_upgrade_kernel() + task_upgrade_selinux(),
    )

    node.reboot()

    provision(
        username="root",
        address=node.address,
        package_source=package_source,
        distribution=node.distribution,
    )
    return node.address


IMAGE_NAMES = {
    'fedora-20': 'Fedora-x86_64-20-20140407-sda',
}


def aws_provisioner(access_key, secret_access_token, keyname,
                    region, security_groups):
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
