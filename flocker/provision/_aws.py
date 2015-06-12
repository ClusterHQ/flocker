# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
AWS provisioner.
"""

from textwrap import dedent
from time import time

from effect.retry import retry
from effect import Effect, Constant

from ._libcloud import LibcloudProvisioner
from ._install import (
    provision,
    task_install_ssh_key,
)

from ._ssh import run_remotely
from ._effect import sequence


_usernames = {
    'centos-7': 'centos',
    'ubuntu-14.04': 'ubuntu',
    'ubuntu-15.04': 'ubuntu',
}


def get_default_username(distribution):
    """
    Return the username available by default on a system.

    :param str distribution: Name of the operating system distribution
    :return str: The username made available by AWS for this distribution.
    """
    return _usernames[distribution]


def provision_aws(node, package_source, distribution, variants):
    """
    Provision flocker on this node.

    :param LibcloudNode node: Node to provision.
    :param PackageSource package_source: See func:`task_install_flocker`
    :param bytes distribution: See func:`task_install_flocker`
    :param set variants: The set of variant configurations to use when
        provisioning
    """
    username = get_default_username(distribution)

    commands = []

    # cloud-init may not have allowed sudo without tty yet, so try SSH key
    # installation for a few more seconds:
    start = []

    def for_ten_seconds(*args, **kwargs):
        if not start:
            start.append(time())
        return Effect(Constant((time() - start[0]) < 30))

    commands.append(run_remotely(
        username=username,
        address=node.address,
        commands=retry(task_install_ssh_key(), for_ten_seconds),
    ))

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
    'centos-7': 'CentOS 7 x86_64 (2014_09_29) EBS HVM'
                '-b7ee8a69-ee97-4a49-9e68-afaee216db2e-ami-d2a117ba.2',
    'ubuntu-14.04': 'ubuntu/images/hvm-ssd/ubuntu-trusty-14.04-amd64-server-20150325',  # noqa
    'ubuntu-15.04': 'ubuntu/images/hvm-ssd/ubuntu-vivid-15.04-amd64-server-20150422',  # noqa
}


def aws_provisioner(access_key, secret_access_token, keyname,
                    region, zone, security_groups):
    """
    Create a LibCloudProvisioner for provisioning nodes on AWS EC2.

    :param bytes access_key: The access_key to connect to AWS with.
    :param bytes secret_access_token: The corresponding secret token.
    :param bytes region: The AWS region in which to launch the instance.
    :param bytes zone: The AWS zone in which to launch the instance.
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

    location = [loc for loc in driver.list_locations()
                if loc.availability_zone.name == zone][0]

    def create_arguments(disk_size):
        return {
            "location": location,
            "ex_securitygroup": security_groups,
            "ex_blockdevicemappings": [
                {"DeviceName": "/dev/sda1",
                 "Ebs": {"VolumeSize": disk_size,
                         "DeleteOnTermination": True,
                         "VolumeType": "gp2"}}
            ],
            # On some operating systems, a tty is requried for sudo.
            # Since AWS systems have a non-root user as the login,
            # disable this, so we can use sudo with conch.
            "ex_userdata": dedent("""\
                #!/bin/sh
                sed -i '/Defaults *requiretty/d' /etc/sudoers
                """)
        }

    provisioner = LibcloudProvisioner(
        driver=driver,
        keyname=keyname,
        image_names=IMAGE_NAMES,
        create_node_arguments=create_arguments,
        provision=provision_aws,
        default_size="m3.large",
        get_default_user=get_default_username,
        use_private_addresses=True,
    )

    return provisioner
