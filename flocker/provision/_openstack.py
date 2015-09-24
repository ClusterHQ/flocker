# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
OpenStack provisioner.
"""

from textwrap import dedent
from time import time

from effect.retry import retry
from effect import Effect, Constant

from ._libcloud import LibcloudProvisioner
from ._install import (
    provision,
    task_install_ssh_key,
    task_open_control_firewall,
)
from ._ssh import run_remotely

from ._effect import sequence

# XXX: Copied from _aws. Needs refactoring
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


def provision_openstack(node, package_source, distribution, variants):
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

    # XXX Copied from _aws.py -- refactor.
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

    commands.append(run_remotely(
        username='root',
        address=node.address,
        commands=sequence([
            provision(
                package_source=package_source,
                distribution=node.distribution,
                variants=variants,
            ),
            # https://clusterhq.atlassian.net/browse/FLOC-1550
            # This should be part of ._install.configure_cluster
            # task_open_control_firewall(node.distribution),
        ]),
    ))

    return sequence(commands)


def openstack_provisioner(auth_url, auth_plugin, username, secret, region,
                          keyname, images, flavor, tenant):
    """
    Create a LibCloudProvisioner for provisioning nodes on openstack.

    :param bytes auth_url: The keystone URL.
    :param bytes auth_plugin: The OpenStack authentication mechanism. One of
        password or apikey.
    :param bytes username: The user to connect to with.
    :param bytes secret: The password or API key associated with the user.
    :param bytes region: The region in which to launch the instance.
    :param bytes keyname: The name of an existing ssh public key configured in
       openstack. The provision step assumes the corresponding private key is
       available from an agent.
    :param dict images: A mapping of supported operating systems to a
        corresponding OpenStack image name or image ID.
    :param bytes flavor: A flavor name or flavor ID available in the target
        OpenStack installation.
    :param bytes tenant: The name of an OpenStack tenant or project.
    """
    # Import these here, so that this can be imported without
    # installng libcloud.
    from libcloud.compute.providers import get_driver, Provider

    # LibCloud chooses OpenStack auth plugins using a weird naming scheme.
    # See https://libcloud.readthedocs.org/en/latest/compute/drivers/openstack.html#connecting-to-the-openstack-installation  # noqa
    auth_versions = {
        "apikey": "2.0_apikey",
        "password": "2.0_password",
    }
    # See https://libcloud.readthedocs.org/en/latest/compute/drivers/openstack.html  # noqa
    driver = get_driver(Provider.OPENSTACK)(
        key=username,
        secret=secret,
        region=region,
        ex_force_auth_url=auth_url,
        ex_force_auth_version=auth_versions[auth_plugin],
        ex_force_service_region=region,
        ex_tenant_name=tenant,
    )

    provisioner = LibcloudProvisioner(
        driver=driver,
        keyname=keyname,
        image_names=images,
        create_node_arguments=lambda **kwargs: {
            "ex_config_drive": "true",
            "ex_userdata": dedent("""\
                #!/bin/sh
                sed -i '/Defaults *requiretty/d' /etc/sudoers
                """),
        },
        provision=provision_openstack,
        default_size=flavor,
        get_default_user=get_default_username,
    )

    return provisioner
