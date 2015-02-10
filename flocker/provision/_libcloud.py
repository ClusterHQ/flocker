# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Helpers for using libcloud.
"""

from characteristic import attributes, Attribute


def _fixed_OpenStackNodeDriver_to_node(self, api_node):
    """
    This is a copy of
    libcloud.compute.drivers.openstack.OpenStack_1_1_NodeDriver._to_node
    from libcloud 0.16.0 to fix
    https://github.com/apache/libcloud/pull/411
    """
    from libcloud.utils.networking import is_public_subnet
    from libcloud.compute.base import Node
    from libcloud.compute.types import NodeState

    public_networks_labels = ['public', 'internet']

    public_ips, private_ips = [], []

    for label, values in api_node['addresses'].items():
        for value in values:
            ip = value['addr']

            is_public_ip = False

            try:
                public_subnet = is_public_subnet(ip)
            except:
                # IPv6
                public_subnet = False

            # Openstack Icehouse sets 'OS-EXT-IPS:type' to 'floating' for
            # public and 'fixed' for private
            explicit_ip_type = value.get('OS-EXT-IPS:type', None)

            if explicit_ip_type == 'floating':
                is_public_ip = True
            elif explicit_ip_type == 'fixed':
                is_public_ip = False
            elif label in public_networks_labels:
                # Try label next
                is_public_ip = True
            elif public_subnet:
                # Check for public subnet
                is_public_ip = True

            if is_public_ip:
                public_ips.append(ip)
            else:
                private_ips.append(ip)

    # Sometimes 'image' attribute is not present if the node is in an error
    # state
    image = api_node.get('image', None)
    image_id = image.get('id', None) if image else None

    if api_node.get("config_drive", "false").lower() == "true":
        config_drive = True
    else:
        config_drive = False

    return Node(
        id=api_node['id'],
        name=api_node['name'],
        state=self.NODE_STATE_MAP.get(api_node['status'],
                                      NodeState.UNKNOWN),
        public_ips=public_ips,
        private_ips=private_ips,
        driver=self,
        extra=dict(
            hostId=api_node['hostId'],
            access_ip=api_node.get('accessIPv4'),
            # Docs says "tenantId", but actual is "tenant_id". *sigh*
            # Best handle both.
            tenantId=api_node.get('tenant_id') or api_node['tenantId'],
            imageId=image_id,
            flavorId=api_node['flavor']['id'],
            uri=next(link['href'] for link in api_node['links'] if
                     link['rel'] == 'self'),
            metadata=api_node['metadata'],
            password=api_node.get('adminPass', None),
            created=api_node['created'],
            updated=api_node['updated'],
            key_name=api_node.get('key_name', None),
            disk_config=api_node.get('OS-DCF:diskConfig', None),
            config_drive=config_drive,
            availability_zone=api_node.get('OS-EXT-AZ:availability_zone',
                                           None),
        ),
    )


def monkeypatch():
    """
    libcloud 0.16.0 has a broken OpenStackNodeDriver._to_node.

    See https://github.com/apache/libcloud/pull/411
    """
    from libcloud import __version__
    if __version__ == "0.16.0":
        from libcloud.compute.drivers.openstack import OpenStack_1_1_NodeDriver
        OpenStack_1_1_NodeDriver._to_node = _fixed_OpenStackNodeDriver_to_node


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


@attributes([
    # _node gets updated, so we can't make this immutable.
    Attribute('_node'),
    Attribute('_provisioner'),
    'address',
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
        """
        self._node.reboot()

        self._node, self.addresses = (
            self._node.driver.wait_until_running([self._node])[0])

    def provision(self, package_source):
        """
        Provision flocker on this node.

        :param PackageSource package_source: The source from which to install
            flocker.
        """
        self._provisioner.provision(
            node=self,
            package_source=package_source,
            distribution=self.distribution,
        )
        return self.address

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
    """

    def create_node(self, name, distribution,
                    userdata=None,
                    size=None, disk_size=8,
                    keyname=None, metadata={}):
        """
        Create a node.

        :param str name: The name of the node.
        :param str distribution: The name of the distribution to
            install on the node.
        :param bytes userdata: User data to pass to the instance.
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
            # XXX: ``ex_keyname`` is specific to EC2 and Rackspace
            # drivers. DigitalOcean supports installation of multiple SSH keys
            # and uses the alternative ``ex_ssh_key_ids`` arguments. This
            # should probably be supplied by the driver specific
            # ``_create_node_arguments`` function rather than hard coded here.
            # See: https://clusterhq.atlassian.net/browse/FLOC-1228
            ex_keyname=keyname,
            ex_userdata=userdata,
            ex_metadata=metadata,
            **create_node_arguments
        )

        node, addresses = self._driver.wait_until_running([node])[0]

        public_address = addresses[0]

        return LibcloudNode(
            provisioner=self,
            node=node, address=public_address,
            distribution=distribution)
