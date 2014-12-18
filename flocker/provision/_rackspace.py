# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Rackspace provisioner.
"""

from libcloud.compute.providers import get_driver, Provider
from characteristic import attributes, Attribute
from ._libcloud import get_size, get_image
from ._install import provision


# _node isn't immutable, since libcloud provides new instances
# with updated data.
@attributes([Attribute('_node'), 'address', 'distribution'])
class RackspaceNode(object):
    def destroy(self):
        self._node.destroy()

    def provision(self, package_source):
        """
        Provision flocker on this node.
        """
        provision(
            self.address, username="root",
            package_source=package_source,
            distribution=self.distribution,
        )
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

    def create_node(self, name, distribution,
                    userdata=None,
                    size="performance1-2", disk_size=8,
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
            ex_config_drive="true",
            ex_metadata=metadata,
        )

        node, addresses = self._driver.wait_until_running([node])[0]

        public_address = addresses[0]

        return RackspaceNode(node=node, address=public_address,
                             distribution=distribution)
