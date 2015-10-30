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

from boto.ec2 import connect_to_region
from boto.ec2.blockdevicemapping import (
    EBSBlockDeviceType, BlockDeviceMapping,
)

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
    # Find an image for the appropriate version at the following URL, then get
    # the name of the image. Both CentOS and Ubuntu use consistent names across
    # all regions.
    # https://wiki.centos.org/Cloud/AWS
    'centos-7': 'CentOS Linux 7 x86_64 HVM EBS 20150928_01-b7ee8a69-ee97-4a49-9e68-afaee216db2e-ami-69327e0c.2',  # noqa
    # https://cloud-images.ubuntu.com/locator/ec2/
    'ubuntu-14.04': 'ubuntu/images/hvm-ssd/ubuntu-trusty-14.04-amd64-server-20151019',  # noqa
    'ubuntu-15.04': 'ubuntu/images/hvm-ssd/ubuntu-vivid-15.04-amd64-server-20151015',  # noqa
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
        while instance.state != 'running':
            with start_action(
                action_type=u"flocker:provision:aws:wait_until_running:sleep",
                instance_state=instance.state,
            ):
                sleep(1)
            instance.update()


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

        def for_thirty_seconds(*args, **kwargs):
            if not start:
                start.append(time())
            return Effect(Constant((time() - start[0]) < 30))

        commands.append(run_remotely(
            username=username,
            address=self.address,
            commands=retry(task_install_ssh_key(), for_thirty_seconds),
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
    """
    A provisioner that creates nodes on AWS.

    :ivar boto.ec2.connection.EC2Connection _connection: The boto connection to
        use.
    :ivar bytes _keyname: The name of an existing ssh public key configured
        with the cloud provider.
    :ivar _security_groups: List of security groups to put the instances
        created by this provisioner in.
    :type _security_groups: `list` of `bytes`
    :param bytes _zone: The AWS availability zone to put instances created by
        this provisioner in.
    """
    _connection = field(mandatory=True)
    _keyname = field(type=bytes, mandatory=True)
    _security_groups = field(mandatory=True)
    _zone = field(type=bytes, mandatory=True)
    _default_size = field(type=bytes, mandatory=True)

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
        if size is None:
            size = self._default_size

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

            images = self._connection.get_all_images(
                filters={'name': IMAGE_NAMES[distribution]},
            )

            with start_action(
                action_type=u"flocker:provision:aws:create_node:run_instances",
            ) as context:
                reservation = self._connection.run_instances(
                    images[0].id,
                    key_name=self._keyname,
                    instance_type=size,
                    security_groups=self._security_groups,
                    block_device_map=diskmap,
                    placement=self._zone,
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

            self._connection.create_tags([instance.id], metadata)

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
    Create an IProvisioner for provisioning nodes on AWS EC2.

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
    conn = connect_to_region(
        region,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_access_token,
    )
    return AWSProvisioner(
        _connection=conn,
        _keyname=keyname,
        _security_groups=security_groups,
        _zone=zone,
        _default_size=b"m3.large",
    )
