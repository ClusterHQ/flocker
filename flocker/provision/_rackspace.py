# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

from libcloud.compute.providers import get_driver, Provider
from characteristic import attributes, Attribute
from ._libcloud import get_size, get_image
from ._install import install


# _node isn't immutable, since libcloud provides new instances
# with updated data.
@attributes([Attribute('_node'), 'address'])
class RackspaceNode(object):
    def destroy(self):
        self._node.destroy()

    def provision(self, distribution, version, branch):
        """
        Provision flocker on this node.
        """
        if distribution != 'fedora-20':
            raise ValueError("Distribution not supported: %r."
                             % (distribution,))
        install([self.address], username="root",
                kwargs={
                    'version': version,
                    'distribution': distribution,
                    'branch': branch,
                    })
        return self.address


IMAGE_NAMES = {
    'fedora-20': u'Fedora 20 (Heisenbug) (PVHVM)',
}


@attributes([Attribute('_keyname')], apply_immutable=True)
class Rackspace(object):

    def __init__(self, username, key, region):
        self._driver = get_driver(Provider.RACKSPACE)(
            key=username,
            secret=key,
            region=region)

    def create_node(self, name,
                    distribution, version, branch,
                    userdata=None,
                    size="performance1-2", disk_size=8,
                    keyname=None,
                    ):
        """
        :param str name: The name of the node.
        :param str base_ami: The name of the ami to use.
        :param bytes userdata: User data to pass to the instance.
        :param bytes size: The name of the size to use.
        :param int disk_size: The size of disk to allocate.
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
            ex_config_drive="true",
        )

        node, addresses = self._driver.wait_until_running([node])[0]

        public_address = addresses[0]

        node = RackspaceNode(node=node, address=public_address)
        node.provision(distribution, version, branch)
        return node
