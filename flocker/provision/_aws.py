# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
AWS provisioner.
"""

from textwrap import dedent
from time import time, sleep

from pyrsistent import PClass, field

from zope.interface import implementer

from effect.retry import retry
from effect import Effect, Constant

from ._common import INode, IProvisioner

from ._install import (
    provision,
    task_install_ssh_key,
)

from eliot import start_action

from ._ssh import run_remotely, run_from_args
from ._effect import sequence


_usernames = {
    'centos-7': 'centos',
    'ubuntu-14.04': 'ubuntu',
    'ubuntu-15.04': 'ubuntu',
}


IMAGE_NAMES = {
    'centos-7': 'CentOS 7 x86_64 (2014_09_29) EBS HVM'
                '-b7ee8a69-ee97-4a49-9e68-afaee216db2e-ami-d2a117ba.2',
    'ubuntu-14.04': 'ubuntu/images/hvm-ssd/ubuntu-trusty-14.04-amd64-server-20150325',  # noqa
    'ubuntu-15.04': 'ubuntu/images/hvm-ssd/ubuntu-vivid-15.04-amd64-server-20150422',  # noqa
}


def _wait_until_running(instance):
    """
    Wait until a instance is running.

    :param boto.ec2.instance.Instance instance: The instance to wait for.
    """
    with start_action(
        action_type=u"flocker:provision:aws:wait_until_running",
        instance_id=instance.id,
    ):
        state = instance.state
        while state != 'running':
            with start_action(
                action_type=u"flocker:provision:aws:wait_until_running:sleep",
                instance_state=instance.state,
            ):
                sleep(1)
            instance.update()
            new_state = instance.state
            if new_state != state:
                state = new_state


@implementer(INode)
class AWSNode(PClass):
    _provisioner = field(mandatory=True)
    _instance = field(mandatory=True)
    distribution = field(mandatory=True)
    name = field(mandatory=True)

    @property
    def address(self):
        return self._instance.ip_address.encode('ascii')

    @property
    def private_address(self):
        return self._instance.private_ip_address.encode('ascii')

    def destroy(self):
        with start_action(
            action_type=u"flocker:provision:aws:destroy",
            instance_id=self._instance.id,
        ):
            self._instance.terminate()

    def get_default_username(self):
        """
        Return the username available by default on a system.
        """
        return _usernames[self.distribution]

    def provision(self, package_source, variants=()):
        """
        Provision flocker on this node.

        :param LibcloudNode node: Node to provision.
        :param PackageSource package_source: See func:`task_install_flocker`
        :param set variants: The set of variant configurations to use when
            provisioning
        """
        username = self.get_default_username()

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
            address=self.address,
            commands=retry(task_install_ssh_key(), for_ten_seconds),
        ))

        commands.append(run_remotely(
            username='root',
            address=self.address,
            commands=provision(
                package_source=package_source,
                distribution=self.distribution,
                variants=variants,
            ),
        ))

        return sequence(commands)

    def reboot(self):
        """
        Reboot the node.

        :return Effect:
        """

        def do_reboot(_):
            with start_action(
                action_type=u"flocker:provision:aws:reboot",
                instance_id=self._instance.id,
            ):
                self._instance.reboot()
                _wait_until_running(self._instance)

        return run_remotely(
            username="root",
            address=self.address,
            commands=run_from_args(["sync"])
        ).on(success=do_reboot)


@implementer(IProvisioner)
class AWSProvisioner(PClass):
    connection = field(mandatory=True)
    keyname = field(mandatory=True)
    security_groups = field(mandatory=True)
    zone = field(mandatory=True)
    default_size = field(mandatory=True)

    def get_ssh_key(self):
        """
        Return the public key associated with the provided keyname.

        :return Key: The ssh public key or ``None`` if it can't be determined.
        """
        # EC2 only provides the SSH2 fingerprint (for uploaded keys)
        # or the SHA-1 hash of the private key (for EC2 generated keys)
        # https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_KeyPairInfo.html
        return None

    def create_node(self, name, distribution,
                    size=None, disk_size=8,
                    metadata={}):
        # Import these here, so that this can be imported without installng
        # libcloud.
        from boto.ec2.blockdevicemapping import (
            EBSBlockDeviceType, BlockDeviceMapping,
        )
        if size is None:
            size = self.default_size

        with start_action(
            action_type=u"flocker:provision:aws:create_node",
            name=name,
            distribution=distribution,
            image_size=size,
            disk_size=disk_size,
            metadata=metadata,
        ):

            metadata = metadata.copy()
            metadata['Name'] = name

            disk1 = EBSBlockDeviceType()
            disk1.size = disk_size
            disk1.delete_on_termination = True
            diskmap = BlockDeviceMapping()
            diskmap['/dev/sda1'] = disk1

            images = self.connection.get_all_images(
                filters={'name': IMAGE_NAMES[distribution]},
            )

            with start_action(
                action_type=u"flocker:provision:aws:create_node:run_instances",
            ) as context:
                reservation = self.connection.run_instances(
                    images[0].id,
                    key_name=self.keyname,
                    instance_type=size,
                    security_groups=self.security_groups,
                    block_device_map=diskmap,
                    placement=self.zone,
                    # On some operating systems, a tty is requried for sudo.
                    # Since AWS systems have a non-root user as the login,
                    # disable this, so we can use sudo with conch.
                    user_data=dedent("""\
                        #!/bin/sh
                        sed -i '/Defaults *requiretty/d' /etc/sudoers
                        """),
                )

                instance = reservation.instances[0]
                context.add_success_fields(instance_id=instance.id)

            self.connection.create_tags([instance.id], metadata)

            # Display state as instance starts up, to keep user informed that
            # things are happening.
            _wait_until_running(instance)

            return AWSNode(
                name=name,
                _provisioner=self,
                _instance=instance,
                distribution=distribution,
            )


def aws_provisioner(access_key, secret_access_token, keyname,
                    region, zone, security_groups):
    """
    Create a IProvisioner for provisioning nodes on AWS EC2.

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
    # Import these here, so that this can be imported without installng
    # libcloud.
    from boto.ec2 import connect_to_region
    conn = connect_to_region(
        region,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_access_token,
    )
    return AWSProvisioner(
        connection=conn,
        keyname=keyname,
        security_groups=security_groups,
        zone=zone,
        default_size="m3.large",
    )
