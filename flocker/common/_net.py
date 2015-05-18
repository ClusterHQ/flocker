# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Network utilities.
"""

import netifaces


def get_all_ips():
    """
    Find all IPs for this machine.

    :return: ``set`` of IP addresses (``bytes``).
    """
    ips = set()
    interfaces = netifaces.interfaces()
    for interface in interfaces:
        addresses = netifaces.ifaddresses(interface)
        for address_family in (netifaces.AF_INET, netifaces.AF_INET6):
            family_addresses = addresses.get(address_family)
            if not family_addresses:
                continue
            for address in family_addresses:
                ips.add(address['addr'])
    return ips
