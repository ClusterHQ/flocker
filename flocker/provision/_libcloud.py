# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Helpers for using libcloud.
"""


def fixed_OpenStackNodeDriver_to_node(self, api_node):
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
        OpenStack_1_1_NodeDriver._to_node = fixed_OpenStackNodeDriver_to_node


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
