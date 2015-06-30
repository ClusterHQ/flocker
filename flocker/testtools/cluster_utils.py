# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Utility functions for test cluster lifecycle management.
"""

from uuid import uuid4, UUID

supported_test_types = ['functional', 'acceptance']
supported_platforms = ['centos-7', 'ubuntu-14.04', 'ubuntu-15.04']
supported_providers = ['aws', 'openstack']


def make_cluster_id(test_type, platform, provider):
    """
    """
    test_index = supported_test_types.index(test_type)
    if test_index == -1:
        raise Exception()
    platform_index = supported_platforms.index(platform)
    if platform_index == -1:
        raise Exception()
    provider_index = supported_providers.index(provider)
    if provider_index == -1:
        raise Exception()

    marker_string = str(test_index) + str(platform_index) + str(provider_index)
    marker = int(marker_string)
    c = uuid4()
    tagged_cluster_id = UUID(fields=(
        c.time_low, c.time_mid, c.time_hi_version,
        c.clock_seq_hi_variant, c.clock_seq_low,
        # Instead of node, a hard-coded magic constant.
        marker,
    ))
    return tagged_cluster_id
