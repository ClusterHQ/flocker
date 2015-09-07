# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Rackspace provisioner.
"""

from ._libcloud import LibcloudProvisioner
from ._install import (
    provision,
    task_open_control_firewall,
)
from ._ssh import run_remotely

from ._effect import sequence


def get_default_username(distribution):
    """
    Return the username available by default on a system.

    :param str distribution: Name of the operating system distribution
    :return str: The username made available by Rackspace for this
        distribution.
    """
    return 'root'


def provision_rackspace(node, package_source, distribution, variants):
    """
    Provision flocker on this node.

    :param LibcloudNode node: Node to provision.
    :param PackageSource package_source: See func:`task_install_flocker`
    :param bytes distribution: See func:`task_install_flocker`
    :param set variants: The set of variant configurations to use when
        provisioning
    """
    commands = []
    commands.append(run_remotely(
        username=get_default_username(distribution),
        address=node.address,
        commands=sequence([
            provision(
                package_source=package_source,
                distribution=node.distribution,
                variants=variants,
            ),
            # https://clusterhq.atlassian.net/browse/FLOC-1550
            # This should be part of ._install.configure_cluster
            task_open_control_firewall(node.distribution),
        ]),
    ))

    return sequence(commands)


IMAGE_NAMES = {
    'centos-7': u'CentOS 7 (PVHVM)',
    'ubuntu-14.04': u'Ubuntu 14.04 LTS (Trusty Tahr) (PVHVM)',
    'ubuntu-15.04': u'Ubuntu 15.04 (Vivid Vervet) (PVHVM)',
}


def rackspace_provisioner(username, key, region, keyname):
    """
    Create a LibCloudProvisioner for provisioning nodes on rackspace.

    :param bytes username: The user to connect to rackspace with.
    :param bytes key: The API key associated with the user.
    :param bytes region: The rackspace region in which to launch the instance.
    :param bytes keyname: The name of an existing ssh public key configured in
       rackspace. The provision step assumes the corresponding private key is
       available from an agent.
    """
    # Import these here, so that this can be imported without
    # installng libcloud.
    from libcloud.compute.providers import get_driver, Provider

    driver = get_driver(Provider.RACKSPACE)(
        key=username,
        secret=key,
        region=region)

    provisioner = LibcloudProvisioner(
        driver=driver,
        keyname=keyname,
        image_names=IMAGE_NAMES,
        create_node_arguments=lambda **kwargs: {
            "ex_config_drive": "true",
        },
        provision=provision_rackspace,
        default_size="performance1-8",
        get_default_user=get_default_username,
    )

    return provisioner
