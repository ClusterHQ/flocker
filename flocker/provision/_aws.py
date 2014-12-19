# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
AWS provisioner.
"""

from characteristic import attributes, Attribute
from ._libcloud import get_size, get_image
from ._install import (
    provision, run_with_fabric,
    task_install_ssh_key,
    task_upgrade_kernel,
)


# _node isn't immutable, since libcloud provides new instances
# with updated data.
@attributes([Attribute('_node'), 'address', 'distribution'])
class AWSNode(object):
    def destroy(self):
        self._node.destroy()

    def provision(self, package_source):
        """
        Provision flocker on this node.
        """
        run_with_fabric(
            username='fedora',
            address=self.address,
            commands=task_install_ssh_key(),
        )
        run_with_fabric(
            username='root',
            address=self.address,
            commands=task_upgrade_kernel(),
        )
        self._node.reboot()

        self._node, self.addresses = \
            self._node.driver.wait_until_running([self._node])[0]

        provision(
            username="root",
            address=self.address,
            package_source=package_source,
            distribution=self.distribution,
        )
        return self.address


IMAGE_NAMES = {
    'fedora-20': 'Fedora-x86_64-20-20140407-sda',
}


@attributes([Attribute('_keyname')], apply_immutable=True)
class AWS(object):

    def __init__(self, access_key, secret_access_token,
                 region, security_groups):
        # Import these here, so that this can be imported without
        # installng libcloud.
        from libcloud.compute.providers import get_driver, Provider
        self._driver = get_driver(Provider.EC2)(
            key=access_key,
            secret=secret_access_token,
            region=region)

        self.security_groups = security_groups

    def create_node(self, name, distribution,
                    userdata=None,
                    size="m3.large", disk_size=8,
                    keyname=None, metadata={}):
        """
        :param str name: The name of the node.
        :param str base_ami: The name of the ami to use.
        :param bytes userdata: User data to pass to the instance.
        :param bytes size: The name of the size to use.
        :param int disk_size: The size of disk to allocate.
        :param dict metadata: Metadata to associate with the node.
        """
        if keyname is None:
            keyname = self._keyname

        image_name = IMAGE_NAMES[distribution]

        node = self._driver.create_node(
            name=name,
            image=get_image(self._driver, image_name),
            size=get_size(self._driver, size),
            ex_keyname=keyname,
            ex_userdata=userdata,
            ex_metadata=metadata,
            ex_securitygroup=self.security_groups,
            ex_blockdevicemappings=[
                {"DeviceName": "/dev/sda1",
                 "Ebs": {"VolumeSize": disk_size,
                         "DeleteOnTermination": True,
                         "VolumeType": "gp2"}}
            ],
        )

        node, addresses = self._driver.wait_until_running([node])[0]

        public_address = addresses[0]

        return AWSNode(node=node, address=public_address,
                       distribution=distribution)
