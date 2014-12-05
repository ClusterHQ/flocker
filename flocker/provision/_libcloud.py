# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Helpers for libcloud.
"""


def get_size(driver, size_name):
    """
    Return a ``NodeSize`` corresponding to the name of size.
    """
    try:
        return [s for s in driver.list_sizes() if s.id == size_name][0]
    except IndexError:
        raise ValueError("Unknown size.", size_name)


def get_image(driver, image_name):
    try:
        return [s for s in driver.list_images() if s.name == image_name][0]
    except IndexError:
        raise ValueError("Unknown image.", image_name)
