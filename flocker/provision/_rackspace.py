# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

import yaml
from libcloud.compute.providers import get_driver, Provider

aws_config = yaml.safe_load(open("aws_config.yml"))

rackspace_config = aws_config['rackspace']

driver = get_driver(Provider.RACKSPACE)(
    key=rackspace_config['username'],
    secret=rackspace_config['key'],
    region=rackspace_config['region'])


def get_size(size_name):
    """
    Return a ``NodeSize`` corresponding to the name of size.
    """
    try:
        return [s for s in driver.list_sizes() if s.id == size_name][0]
    except IndexError:
        raise ValueError("Unknown size.", size_name)


def get_image(image_name):
    try:
        return [s for s in driver.list_images() if s.name == image_name][0]
    except IndexError:
        raise ValueError("Unknown image.", image_name)


def create_node(name, image_name,
                userdata=None,
                size="performance1-2", disk_size=8,
                keyname=rackspace_config['keyname']):
    """
    :param str name: The name of the node.
    :param str base_ami: The name of the ami to use.
    :param bytes userdata: User data to pass to the instance.
    :param bytes size: The name of the size to use.
    :param int disk_size: The size of disk to allocate.
    """
    node = driver.create_node(
        name=name,
        image=get_image(image_name),
        size=get_size(size),
        ex_keyname=keyname,
        ex_userdata=userdata,
        ex_config_drive="true",
    )
    return node
