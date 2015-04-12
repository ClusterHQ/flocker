# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
AWS provisioner.
"""

from ._libcloud import LibcloudProvisioner
from ._common import Variants
from ._install import (
    provision,
    task_install_ssh_key,
    task_upgrade_kernel,
    task_upgrade_kernel_centos,
    task_enable_updates_testing
)

from ._ssh import run_remotely
from ._effect import sequence
from effect import Func, Effect


def provision_aws(node, package_source, distribution, variants):
    """
    Provision flocker on this node.

    :param LibcloudNode node: Node to provision.
    :param PackageSource package_source: See func:`task_install_flocker`
    :param bytes distribution: See func:`task_install_flocker`
    :param set variants: The set of variant configurations to use when
        provisioning
    """
    username = {
        'fedora-20': 'fedora',
        'centos-7': 'centos',
    }[distribution]

    commands = []

    commands.append(run_remotely(
        username=username,
        address=node.address,
        commands=task_install_ssh_key(),
    ))

    pre_reboot_commands = []
    if Variants.DISTRO_TESTING in variants:
        pre_reboot_commands.append(
            task_enable_updates_testing(distribution)
        )

    if distribution in ('centos-7',):
        pre_reboot_commands.append(
            task_upgrade_kernel_centos()
        )

    elif distribution in ('fedora-20',):
        pre_reboot_commands.append(
            task_upgrade_kernel(),
        )

    commands.append(run_remotely(
        username='root',
        address=node.address,
        commands=sequence(pre_reboot_commands),
    ))

    commands.append(Effect(Func(node.reboot)))

    commands.append(run_remotely(
        username='root',
        address=node.address,
        commands=provision(
            package_source=package_source,
            distribution=node.distribution,
            variants=variants,
        ),
    ))

    return sequence(commands)


IMAGE_NAMES = {
    'fedora-20': 'Fedora-x86_64-20-20140407-sda',
    'centos-7': 'CentOS 7 x86_64 (2014_09_29) EBS HVM'
                '-b7ee8a69-ee97-4a49-9e68-afaee216db2e-ami-d2a117ba.2',
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
    # installing libcloud.
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
