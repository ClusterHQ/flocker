# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Helpers for using libcloud.
"""

from zope.interface import (
    Attribute as InterfaceAttribute, Interface, implementer)
from characteristic import attributes, Attribute

from flocker.provision._ssh import run_remotely, run_from_args


def get_size(driver, size_id):
    """
    Return a ``NodeSize`` corresponding to a given id.

    :param driver: The libcloud driver to query for sizes.
    """
    try:
        return [s for s in driver.list_sizes() if s.id == size_id][0]
    except IndexError:
        raise ValueError("Unknown size.", size_id)


def get_image(driver, image_name):
    """
    Return a ``NodeImage`` corresponding to a given name of size.

    :param driver: The libcloud driver to query for images.
    """
    try:
        return [s for s in driver.list_images() if s.name == image_name][0]
    except IndexError:
        raise ValueError("Unknown image.", image_name)


class INode(Interface):
    """
    Interface for node for running acceptance tests.
    """
    address = InterfaceAttribute('Public IP address for node')
    private_address = InterfaceAttribute('Private IP address for node')
    distribution = InterfaceAttribute('distribution on node')

    def get_default_username():
        """
        Return the username available by default on a system.

        Some cloud systems (e.g. AWS) provide a specific username, which
        depends on the OS distribution started.  This method returns
        the username based on the node distribution.
        """

    def provision(package_source, variants):
        """
        Provision flocker on this node.

        :param PackageSource package_source: The source from which to install
            flocker.
        :param set variants: The set of variant configurations to use when
            provisioning
        """


@implementer(INode)
@attributes([
    # _node gets updated, so we can't make this immutable.
    Attribute('_node'),
    Attribute('_provisioner'),
    'address',
    'private_address',
    'distribution',
])
class LibcloudNode(object):
    """
    A node created with libcloud.

    :ivar Node _node: The libcloud node object.
    :ivar LibcloudProvisioner _provisioner: The provisioner that created this
        node.
    :ivar bytes address: The IP address of the node.
    :ivar str distribution: The distribution installed on the node.
    :ivar bytes name: The name of the node.
    """

    def destroy(self):
        """
        Destroy the node.
        """
        self._node.destroy()

    def reboot(self):
        """
        Reboot the node.

        :return Effect:
        """

        def do_reboot(_):
            self._node.reboot()
            self._node, self.addresses = (
                self._node.driver.wait_until_running([self._node])[0])
            return

        return run_remotely(
            username="root",
            address=self.address,
            commands=run_from_args(["sync"])
        ).on(success=do_reboot)

    def get_default_username(self):
        """
        Return the default username on this provisioner.
        """
        return self._provisioner.get_default_user(self.distribution)

    def provision(self, package_source, variants=()):
        """
        Provision flocker on this node.

        :param PackageSource package_source: The source from which to install
            flocker.
        :param set variants: The set of variant configurations to use when
            provisioning
        """
        return self._provisioner.provision(
            node=self,
            package_source=package_source,
            distribution=self.distribution,
            variants=variants,
        ).on(success=lambda _: self.address)

    @property
    def name(self):
        return self._node.name


@attributes([
    Attribute('_driver'),
    Attribute('_keyname'),
    Attribute('image_names'),
    Attribute('_create_node_arguments'),
    Attribute('provision'),
    Attribute('default_size'),
    Attribute('get_default_user'),
    Attribute('use_private_addresses', instance_of=bool, default_value=False),
], apply_immutable=True)
class LibcloudProvisioner(object):
    """
    :ivar libcloud.compute.base.NodeDriver driver: The libcloud driver to use.
    :ivar bytes _keyname: The name of an existing ssh public key configured
        with the cloud provider. The provision step assumes the corresponding
        private key is available from an agent.
    :ivar dict image_names: Dictionary mapping distributions to cloud image
        names.
    :ivar callable _create_node_arguments: Extra arguments to pass to
        libcloud's ``create_node``.
    :ivar callable provision: Function to call to provision a node.
    :ivar str default_size: Name of the default size of node to create.
    :ivar callable get_default_user: Function to provide the default
        username on the node.
    :ivar bool use_private_addresses: Whether the `private_address` of nodes
        should be populated. This should be specified if the cluster nodes
        use the private address for inter-node communication.
    """

    def create_node(self, name, distribution,
                    size=None, disk_size=8,
                    keyname=None, metadata={}):
        """
        Create a node.

        :param str name: The name of the node.
        :param str distribution: The name of the distribution to
            install on the node.
        :param str size: The name of the size to use.
        :param int disk_size: The size of disk to allocate.
        :param dict metadata: Metadata to associate with the node.
        :param bytes keyname: The name of an existing ssh public key configured
            with the cloud provider. The provision step assumes the
            corresponding private key is available from an agent.

        :return libcloud.compute.base.Node: The created node.
        """
        if keyname is None:
            keyname = self._keyname

        if size is None:
            size = self.default_size

        image_name = self.image_names[distribution]

        create_node_arguments = self._create_node_arguments(
            disk_size=disk_size)

        node = self._driver.create_node(
            name=name,
            image=get_image(self._driver, image_name),
            size=get_size(self._driver, size),
            ex_keyname=keyname,
            ex_metadata=metadata,
            **create_node_arguments
        )

        node, addresses = self._driver.wait_until_running([node])[0]

        public_address = addresses[0]

        if self.use_private_addresses:
            private_address = node.private_ips[0]
        else:
            private_address = None

        return LibcloudNode(
            provisioner=self,
            node=node, address=public_address,
            private_address=private_address,
            distribution=distribution)
